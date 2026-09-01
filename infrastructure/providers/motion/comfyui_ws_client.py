from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import aiohttp

from core.domain.exceptions import (
    ProviderConnectionError,
    ProviderError,
    ProviderTimeoutError,
)


class ComfyUIWsClient:
    """Small async ComfyUI HTTP/WebSocket client with typed provider errors."""

    _SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

    def __init__(
        self,
        server_address: str,
        *,
        timeout_seconds: float = 900.0,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
    ) -> None:
        if not server_address.strip():
            raise ValueError("ComfyUI server_address must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("ComfyUI timeout_seconds must be greater than zero.")
        address = server_address.strip().rstrip("/")
        if "://" not in address:
            address = f"http://{address}"
        parsed = urlparse(address)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ComfyUI server_address must be an HTTP(S) address.")
        self._http_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        websocket_scheme = "wss" if parsed.scheme == "https" else "ws"
        self._ws_base = f"{websocket_scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session_factory = session_factory

    async def upload_image(self, image_bytes: bytes, storage_key: str) -> str:
        if not image_bytes:
            raise ProviderError("ComfyUI input image is empty.")
        suffix = PurePosixPath(storage_key.replace("\\", "/")).suffix.casefold()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix)
        if content_type is None:
            raise ProviderError("ComfyUI input image type is unsupported.")
        original = PurePosixPath(storage_key.replace("\\", "/")).name
        safe_name = self._SAFE_FILENAME.sub("-", original) or f"input{suffix}"
        filename = f"selma-motion-{uuid.uuid4().hex}-{safe_name}"
        form = aiohttp.FormData()
        form.add_field("image", image_bytes, filename=filename, content_type=content_type)
        form.add_field("type", "input")
        form.add_field("overwrite", "true")
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        try:
            async with (
                self._session_factory(timeout=timeout) as session,
                session.post(f"{self._http_base}/upload/image", data=form) as response,
            ):
                if response.status not in {200, 201}:
                    raise ProviderError(
                        f"ComfyUI image upload failed ({response.status}): {await response.text()}"
                    )
                payload = await response.json()
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError("ComfyUI image upload timed out.") from error
        except aiohttp.ClientError as error:
            raise ProviderConnectionError(f"ComfyUI image upload failed: {error}") from error
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ProviderError("ComfyUI image upload returned no filename.")
        subfolder = str(payload.get("subfolder", "")).strip("/\\")
        return f"{subfolder}/{name}" if subfolder else name

    async def queue_prompt_and_wait(
        self,
        prompt: dict[str, Any],
        client_id: str | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> dict[str, Any]:
        if not prompt:
            raise ProviderError("ComfyUI prompt graph must not be empty.")
        resolved_client_id = client_id or uuid.uuid4().hex
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        try:
            async with (
                self._session_factory(timeout=timeout) as session,
                session.ws_connect(
                    f"{self._ws_base}/ws", params={"clientId": resolved_client_id}
                ) as websocket,
            ):
                async with session.post(
                    f"{self._http_base}/prompt",
                    json={"prompt": prompt, "client_id": resolved_client_id},
                ) as response:
                    if response.status != 200:
                        raise ProviderError(
                            f"ComfyUI queue failed ({response.status}): {await response.text()}"
                        )
                    payload = await response.json()
                prompt_id = str(payload.get("prompt_id", "")).strip()
                if not prompt_id:
                    raise ProviderError("ComfyUI queue returned no prompt_id.")
                await self._wait_for_execution(
                    websocket,
                    prompt_id=prompt_id,
                    prompt=prompt,
                    progress_callback=progress_callback,
                )
                async with session.get(
                    f"{self._http_base}/history/{prompt_id}"
                ) as response:
                    if response.status != 200:
                        raise ProviderError(
                            f"ComfyUI history failed ({response.status}): {await response.text()}"
                        )
                    history_payload = await response.json()
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError(
                f"ComfyUI execution timed out after {self._timeout_seconds:g} seconds."
            ) from error
        except aiohttp.ClientError as error:
            raise ProviderConnectionError(f"ComfyUI connection failed: {error}") from error
        history = history_payload.get(prompt_id)
        if not isinstance(history, dict):
            raise ProviderError("ComfyUI history did not contain the completed prompt.")
        return {**history, "prompt_id": prompt_id}

    async def download_output(self, file_info: dict[str, Any]) -> bytes:
        filename = str(file_info.get("filename", "")).strip()
        if not filename:
            raise ProviderError("ComfyUI output does not contain a filename.")
        params = {
            "filename": filename,
            "subfolder": str(file_info.get("subfolder", "")),
            "type": str(file_info.get("type", "output")),
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        try:
            async with (
                self._session_factory(timeout=timeout) as session,
                session.get(f"{self._http_base}/view", params=params) as response,
            ):
                if response.status != 200:
                    raise ProviderError(
                        f"ComfyUI output download failed ({response.status})."
                    )
                data = await response.read()
        except asyncio.TimeoutError as error:
            raise ProviderTimeoutError("ComfyUI output download timed out.") from error
        except aiohttp.ClientError as error:
            raise ProviderConnectionError(f"ComfyUI output download failed: {error}") from error
        if not data:
            raise ProviderError("ComfyUI returned an empty output file.")
        return data

    async def _wait_for_execution(
        self,
        websocket: Any,
        *,
        prompt_id: str,
        prompt: dict[str, Any],
        progress_callback: Callable[[float], None] | None,
    ) -> None:
        current_node = ""
        last_progress = 0.0
        while True:
            message = await websocket.receive()
            if message.type == aiohttp.WSMsgType.ERROR:
                raise ProviderConnectionError("ComfyUI WebSocket reported an error.")
            if message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE}:
                raise ProviderConnectionError("ComfyUI WebSocket closed before completion.")
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                event = json.loads(message.data)
            except (TypeError, json.JSONDecodeError):
                continue
            event_type = str(event.get("type", ""))
            data = event.get("data", {})
            if not isinstance(data, dict) or str(data.get("prompt_id", prompt_id)) != prompt_id:
                continue
            if event_type == "execution_error":
                detail = str(data.get("exception_message", "unknown execution error"))
                raise ProviderError(f"ComfyUI execution failed: {detail}")
            if event_type == "executing":
                node = data.get("node")
                if node is None:
                    if progress_callback is not None and last_progress < 1.0:
                        progress_callback(1.0)
                    return
                current_node = str(node)
            elif event_type == "progress" and progress_callback is not None:
                maximum = float(data.get("max", 0) or 0)
                value = float(data.get("value", 0) or 0)
                if maximum <= 0:
                    continue
                node = prompt.get(current_node, {})
                pass_number = int(node.get("_meta", {}).get("selma_pass", 1))
                raw = max(0.0, min(1.0, value / maximum))
                mapped = raw * 0.5 if pass_number == 1 else 0.5 + raw * 0.5
                last_progress = max(last_progress, mapped)
                progress_callback(last_progress)
