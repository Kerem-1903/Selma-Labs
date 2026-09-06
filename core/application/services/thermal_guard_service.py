"""Thermal guard — spec §3.

Policy:
  * minimum delay between jobs (always applied)
  * if GPU temperature is measurable and above threshold, poll until it drops
    below the threshold or the max wait elapses -> PAUSED_THERMAL
  * if temperature is not measurable, only the minimum delay applies and the
    report records that temperature is unsupported.

The probe is injected: production uses ``nvidia_smi_probe``; tests inject a
fake. Clock and sleep are also injectable.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

from core.domain.value_objects.production_infra import (
    PAUSED_THERMAL,
    ThermalDecision,
    ThermalPolicy,
)


def nvidia_smi_probe() -> float | None:
    """Return current GPU temperature in Celsius, or None if unsupported."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class ThermalGuardService:
    def __init__(
        self,
        policy: ThermalPolicy | None = None,
        probe: Callable[[], float | None] = nvidia_smi_probe,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or ThermalPolicy()
        self._probe = probe
        self._clock = clock
        self._sleep = sleep
        self._last_job_end: float | None = None

    # -- lifecycle ----------------------------------------------------------
    def before_job(self) -> ThermalDecision:
        """Apply the minimum inter-job delay. Call right before submitting."""
        waited = 0.0
        if self._last_job_end is not None:
            elapsed = self._clock() - self._last_job_end
            remaining = self.policy.minimum_inter_job_delay_sec - elapsed
            if remaining > 0:
                self._sleep(remaining)
                waited = remaining
        return ThermalDecision(waited_sec=waited, paused=False)

    def after_job(self) -> ThermalDecision:
        """Record job end and cool down if the GPU is above threshold."""
        self._last_job_end = self._clock()
        temperature = self._probe()
        if temperature is None:
            waited = float(self.policy.minimum_inter_job_delay_sec)
            if waited > 0:
                self._sleep(waited)
            return ThermalDecision(
                waited_sec=waited,
                paused=False,
                temperature_celsius=None,
                temperature_supported=False,
            )
        waited = 0.0
        deadline = self._clock() + self.policy.thermal_max_wait_sec
        while temperature > self.policy.thermal_threshold_celsius:
            if self._clock() >= deadline:
                return ThermalDecision(
                    waited_sec=waited,
                    paused=True,  # -> PAUSED_THERMAL
                    temperature_celsius=temperature,
                    temperature_supported=True,
                )
            self._sleep(self.policy.thermal_poll_interval_sec)
            waited += self.policy.thermal_poll_interval_sec
            temperature = self._probe()
        return ThermalDecision(
            waited_sec=waited,
            paused=False,
            temperature_celsius=temperature,
            temperature_supported=True,
        )

    # -- status -------------------------------------------------------------
    def status(self) -> str:
        temperature = self._probe()
        if temperature is None:
            return "OK (temperature unsupported; min-delay only)"
        if temperature > self.policy.thermal_threshold_celsius:
            return PAUSED_THERMAL
        return "OK"
