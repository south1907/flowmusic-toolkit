"""Request/response bridge between FastAPI and the Chrome extension."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Optional

from fastapi import WebSocket


class BridgeUnavailable(RuntimeError):
    pass


class BrowserBridge:
    def __init__(self) -> None:
        self._socket: Optional[WebSocket] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._metadata: dict[str, Any] = {}
        self._connected_at: Optional[float] = None
        self._send_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._socket is not None

    @property
    def status(self) -> dict[str, Any]:
        return {
            "extension_connected": self.connected,
            "connected_at": self._connected_at,
            "extension": self._metadata,
        }

    async def attach(self, socket: WebSocket) -> None:
        previous = self._socket
        self._socket = socket
        self._metadata = {}
        self._connected_at = time.time()
        if previous is not None and previous is not socket:
            await previous.close(code=1012, reason="Replaced by a newer extension connection")

    def detach(self, socket: WebSocket) -> None:
        if socket is not self._socket:
            return
        self._socket = None
        self._connected_at = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(BridgeUnavailable("Chrome extension disconnected"))
        self._pending.clear()

    async def handle_message(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if message.get("type") == "hello":
            self._metadata = {
                "version": message.get("version"),
                "flowmusic_tab_open": message.get("flowmusicTabOpen", False),
            }
            return
        request_id = message.get("id")
        if not request_id:
            return
        future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(message)

    async def request(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        socket = self._socket
        if socket is None:
            raise BridgeUnavailable(
                "Chrome extension is not connected. Load extension/ and keep Flow Music signed in."
            )
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with self._send_lock:
                await socket.send_json(
                    {
                        "type": "request",
                        "id": request_id,
                        "action": "flowmusic_fetch",
                        "payload": payload,
                    }
                )
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise BridgeUnavailable(f"Browser request timed out after {timeout:g}s") from exc
        finally:
            self._pending.pop(request_id, None)


bridge = BrowserBridge()
