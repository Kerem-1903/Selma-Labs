"""ComfyUI job watchdog — spec §12.

Generic and transport-injected so it can wrap any ComfyUI job path:
  * ``submit``  -> returns a prompt_id (called per attempt)
  * ``poll``    -> returns an opaque progress signature for a prompt_id
                   (must be cheap; e.g. history JSON digest)
  * ``finished``-> returns the job result when the job is done, else None
  * ``interrupt`` -> controlled /interrupt (only called when we own the queue)
  * ``queue_has_foreign_jobs`` -> True when other prompts are pending that are
    not ours; in that case interrupting is refused (spec §12).

Timing is injected (clock/sleep) for deterministic unit tests.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from core.domain.value_objects.production_infra import (
    WatchdogOutcome,
    WatchdogPolicy,
)

T = TypeVar("T")


class WatchdogError(RuntimeError):
    """Watchdog exhausted attempts or hit an unrecoverable condition."""


class InterruptRefusedError(WatchdogError):
    """Interrupt was needed but refused because the queue has foreign jobs."""


class ComfyJobWatchdog:
    def __init__(
        self,
        policy: WatchdogPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or WatchdogPolicy()
        self._clock = clock
        self._sleep = sleep

    def run(
        self,
        submit: Callable[[int], str],
        poll: Callable[[str], str],
        finished: Callable[[str], T | None],
        interrupt: Callable[[str], None],
        queue_has_foreign_jobs: Callable[[], bool] | None = None,
        on_new_seed: Callable[[int], int] | None = None,
    ) -> tuple[T, WatchdogOutcome]:
        """Run a job under the watchdog. Returns (result, outcome).

        ``submit(attempt)`` receives the zero-based attempt number. Retry uses
        the same submit callable; seed variation is the caller's job via
        ``on_new_seed`` (called with the attempt when retrying).
        """
        last_error = ""
        for attempt in range(self.policy.retry_limit + 1):
            if attempt > 0 and on_new_seed is not None:
                on_new_seed(attempt)
            prompt_id = submit(attempt)
            try:
                result = self._run_single(
                    prompt_id=prompt_id,
                    poll=poll,
                    finished=finished,
                    interrupt=interrupt,
                    queue_has_foreign_jobs=queue_has_foreign_jobs,
                )
            except _JobStuck as exc:
                last_error = str(exc)
                continue
            return result, WatchdogOutcome(
                ok=True, attempts=attempt + 1, prompt_id=prompt_id,
                reason="completed",
            )
        raise WatchdogError(
            f"job failed after {self.policy.retry_limit + 1} attempts; "
            f"last error: {last_error}"
        )

    async def run_async(
        self,
        submit: Callable[[int], Awaitable[str]],
        poll: Callable[[str], Awaitable[str]],
        finished: Callable[[str], Awaitable[T | None]],
        interrupt: Callable[[str], Awaitable[None]],
        queue_has_foreign_jobs: Callable[[], Awaitable[bool]] | None = None,
        on_new_seed: Callable[[int], None] | None = None,
    ) -> tuple[T, WatchdogOutcome]:
        """Async transport variant used by the aiohttp ComfyUI provider."""
        last_error = ""
        for attempt in range(self.policy.retry_limit + 1):
            if attempt > 0 and on_new_seed is not None:
                on_new_seed(attempt)
            prompt_id = await submit(attempt)
            try:
                result = await self._run_single_async(
                    prompt_id=prompt_id,
                    poll=poll,
                    finished=finished,
                    interrupt=interrupt,
                    queue_has_foreign_jobs=queue_has_foreign_jobs,
                )
            except _JobStuck as error:
                last_error = str(error)
                continue
            return result, WatchdogOutcome(
                ok=True,
                attempts=attempt + 1,
                prompt_id=prompt_id,
                reason="completed",
            )
        raise WatchdogError(
            f"job failed after {self.policy.retry_limit + 1} attempts; "
            f"last error: {last_error}"
        )

    async def _run_single_async(
        self,
        *,
        prompt_id: str,
        poll: Callable[[str], Awaitable[str]],
        finished: Callable[[str], Awaitable[T | None]],
        interrupt: Callable[[str], Awaitable[None]],
        queue_has_foreign_jobs: Callable[[], Awaitable[bool]] | None,
    ) -> T:
        start = asyncio.get_running_loop().time()
        last_signature = ""
        last_change = start
        interrupted = False
        while True:
            now = asyncio.get_running_loop().time()
            if now - start >= self.policy.absolute_job_timeout_sec:
                await self._safe_interrupt_async(
                    prompt_id, interrupt, queue_has_foreign_jobs
                )
                raise _JobStuck(
                    f"absolute timeout {self.policy.absolute_job_timeout_sec:g}s "
                    "without completion"
                )
            signature = await poll(prompt_id)
            if signature != last_signature:
                last_signature = signature
                last_change = now
            elif now - last_change >= self.policy.no_progress_timeout_sec:
                if not interrupted:
                    await self._safe_interrupt_async(
                        prompt_id, interrupt, queue_has_foreign_jobs
                    )
                    interrupted = True
                if now - last_change >= self.policy.no_progress_timeout_sec * 1.5:
                    raise _JobStuck(
                        f"no progress for {self.policy.no_progress_timeout_sec:g}s "
                        "even after interrupt"
                    )
            done = await finished(prompt_id)
            if done is not None:
                return done
            await asyncio.sleep(min(1.0, self.policy.no_progress_timeout_sec / 10))

    @staticmethod
    async def _safe_interrupt_async(
        prompt_id: str,
        interrupt: Callable[[str], Awaitable[None]],
        queue_has_foreign_jobs: Callable[[], Awaitable[bool]] | None,
    ) -> None:
        if queue_has_foreign_jobs is not None and await queue_has_foreign_jobs():
            raise InterruptRefusedError(
                "interrupt refused: queue contains foreign jobs "
                "(spec §12 requires a dedicated instance or sole queue ownership)"
            )
        await interrupt(prompt_id)

    def _run_single(
        self,
        prompt_id: str,
        poll: Callable[[str], str],
        finished: Callable[[str], T | None],
        interrupt: Callable[[str], None],
        queue_has_foreign_jobs: Callable[[], bool] | None,
    ) -> T:
        start = self._clock()
        last_signature = ""
        last_change = start
        interrupted = False
        while True:
            now = self._clock()
            if now - start >= self.policy.absolute_job_timeout_sec:
                self._safe_interrupt(prompt_id, interrupt, queue_has_foreign_jobs)
                raise _JobStuck(
                    f"absolute timeout {self.policy.absolute_job_timeout_sec:g}s "
                    "without completion"
                )
            signature = poll(prompt_id)
            if signature != last_signature:
                last_signature = signature
                last_change = now
            elif now - last_change >= self.policy.no_progress_timeout_sec:
                if not interrupted:
                    self._safe_interrupt(prompt_id, interrupt, queue_has_foreign_jobs)
                    interrupted = True
                if now - last_change >= self.policy.no_progress_timeout_sec * 1.5:
                    raise _JobStuck(
                        f"no progress for {self.policy.no_progress_timeout_sec:g}s "
                        "even after interrupt"
                    )
            done = finished(prompt_id)
            if done is not None:
                return done
            self._sleep(min(1.0, self.policy.no_progress_timeout_sec / 10))

    @staticmethod
    def _safe_interrupt(
        prompt_id: str,
        interrupt: Callable[[str], None],
        queue_has_foreign_jobs: Callable[[], bool] | None,
    ) -> None:
        if queue_has_foreign_jobs is not None and queue_has_foreign_jobs():
            raise InterruptRefusedError(
                "interrupt refused: queue contains foreign jobs "
                "(spec §12 requires a dedicated instance or sole queue ownership)"
            )
        interrupt(prompt_id)


class _JobStuck(RuntimeError):
    """Internal: the job did not complete; watchdog may retry."""
