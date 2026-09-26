"""Flow Music first-party web client executed through the signed-in tab."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from typing import Any, Optional
from urllib.parse import quote

from app.bridge import BridgeUnavailable, BrowserBridge, bridge
from app.config import settings


class FlowMusicError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


_ALLOWED_PATHS = (
    re.compile(r"^/__api/projects$"),
    re.compile(r"^/__api/conversation$"),
    re.compile(r"^/__api/messages/[^/?]+/stream\?last_id=\d+$"),
    re.compile(r"^/__api/audio-create-song-status/[^/?]+$"),
    re.compile(r"^/__api/download/audio/[^/?]+\?format=(?:m4a|wav)$"),
)


def _validate_path(path: str) -> None:
    if not any(pattern.fullmatch(path) for pattern in _ALLOWED_PATHS):
        raise FlowMusicError("Unsupported Flow Music endpoint", 400)


def parse_sse(stream: str, job_id: str = "") -> dict[str, Any]:
    """Extract every operation/clip pair from a conversation SSE snapshot."""
    result: dict[str, Any] = {
        "conversation_id": None,
        "operation_id": None,
        "clip_id": None,
        "operation_ids": [],
        "clip_ids": [],
        "operations": [],
    }
    normalized = stream.replace("\r\n", "\n")
    if "Stream not found" in normalized:
        raise FlowMusicError(f"Flow Music stream not found for job {job_id}", 404)

    for block in re.split(r"\n\s*\n", normalized):
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if not data_lines:
            continue
        try:
            data = json.loads("\n".join(data_lines))
        except (TypeError, ValueError):
            continue
        if event == "conversation_id" and isinstance(data, dict):
            if isinstance(data.get("id"), str):
                result["conversation_id"] = data["id"]
        elif event == "part" and isinstance(data, dict):
            part = data.get("part")
            content = part.get("content") if isinstance(part, dict) else None
            if isinstance(content, dict):
                operation_id = content.get("operation_id")
                clip_id = content.get("clip_id")
                operation_id = operation_id if isinstance(operation_id, str) else None
                clip_id = clip_id if isinstance(clip_id, str) else None
                if operation_id:
                    result["operation_id"] = operation_id
                    if operation_id not in result["operation_ids"]:
                        result["operation_ids"].append(operation_id)
                        result["operations"].append({
                            "operation_id": operation_id,
                            "clip_id": clip_id,
                        })
                    elif clip_id:
                        for operation in result["operations"]:
                            if operation["operation_id"] == operation_id:
                                operation["clip_id"] = clip_id
                                break
                if clip_id:
                    result["clip_id"] = clip_id
                    if clip_id not in result["clip_ids"]:
                        result["clip_ids"].append(clip_id)
                    if not operation_id:
                        result["operations"].append({
                            "operation_id": None,
                            "clip_id": clip_id,
                        })
    return result


def _clip_ids_from_status(status: dict[str, Any]) -> list[str]:
    """Accept current and plausible multi-clip variants of the private API."""
    found: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            if value and value not in found:
                found.append(value)
        elif isinstance(value, list):
            for item in value:
                add(item)
        elif isinstance(value, dict):
            direct = value.get("clip_id") or value.get("id")
            if isinstance(direct, str):
                add(direct)
            else:
                for item in value.values():
                    add(item)

    add(status.get("clip_id"))
    add(status.get("clip_ids"))
    add(status.get("clips"))
    return found


class FlowMusicClient:
    def __init__(self, browser_bridge: BrowserBridge = bridge):
        self.bridge = browser_bridge

    async def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Optional[dict[str, Any]] = None,
        response_mode: str = "json",
        timeout: Optional[float] = None,
    ) -> Any:
        _validate_path(path)
        try:
            response = await self.bridge.request(
                {
                    "path": path,
                    "method": method,
                    "body": body,
                    "responseMode": response_mode,
                },
                timeout=timeout or settings.request_timeout,
            )
        except BridgeUnavailable as exc:
            raise FlowMusicError(str(exc), 503) from exc

        if response.get("error"):
            raise FlowMusicError(str(response["error"]), int(response.get("status") or 502))
        status = int(response.get("status") or 502)
        if status >= 400:
            detail = response.get("data") or f"HTTP {status}"
            if status in {401, 403}:
                detail = "Flow Music session is not authorized; sign in again in the Chrome tab"
            raise FlowMusicError(f"Flow Music request failed ({status}): {detail}", status)
        return response.get("data")

    async def generate(
        self,
        *,
        prompt: str,
    ) -> dict[str, Any]:
        content = prompt.strip()
        project_title = next(
            (line.strip() for line in content.splitlines() if line.strip()),
            "Untitled song",
        )[:100]
        project = await self._request(
            "/__api/projects",
            method="POST",
            body={"title": project_title, "description": content},
        )
        target_project_id = project.get("id") if isinstance(project, dict) else None
        if not target_project_id:
            raise FlowMusicError("Flow Music did not return a project id")

        response = await self._request(
            "/__api/conversation",
            method="POST",
            body={
                "parts": [{"content": content, "part_kind": "user-prompt"}],
                "client_context": {},
                "project_id": target_project_id,
            },
        )
        provider_job_id = response.get("job_id") if isinstance(response, dict) else None
        if not provider_job_id:
            raise FlowMusicError("Flow Music did not return a conversation job id")
        return {
            "provider_job_id": provider_job_id,
            "project_id": target_project_id,
            "status": "pending",
        }

    async def get_job(self, provider_job_id: str) -> dict[str, Any]:
        encoded_job = quote(provider_job_id, safe="")
        stream = await self._request(
            f"/__api/messages/{encoded_job}/stream?last_id=0",
            response_mode="text",
        )
        parsed = parse_sse(str(stream or ""), provider_job_id)
        operation_ids = parsed["operation_ids"]
        if not operation_ids:
            return {"status": "pending", **parsed, "clips": []}

        statuses: list[dict[str, Any]] = []
        clip_ids = list(parsed["clip_ids"])
        duration_by_clip: dict[str, Any] = {}
        failed_states = {"failed", "error", "cancelled", "canceled"}
        completed_states = {"completed", "complete", "success", "succeeded", "done"}
        errors = []
        progress_values = []
        for operation_id in operation_ids:
            operation = await self._request(
                f"/__api/audio-create-song-status/{quote(operation_id, safe='')}"
            )
            operation = operation if isinstance(operation, dict) else {}
            provider_status = str(operation.get("status") or "processing").lower()
            statuses.append({"operation_id": operation_id, "status": provider_status})
            operation_clips = _clip_ids_from_status(operation)
            if not operation_clips:
                operation_clips = [
                    item["clip_id"]
                    for item in parsed["operations"]
                    if item["operation_id"] == operation_id and item.get("clip_id")
                ]
            for clip_id in operation_clips:
                if clip_id not in clip_ids:
                    clip_ids.append(clip_id)
                duration_by_clip[clip_id] = operation.get("duration_s")
            if isinstance(operation.get("progress"), (int, float)):
                progress_values.append(float(operation["progress"]))
            if provider_status in failed_states:
                errors.append({
                    "operation_id": operation_id,
                    "code": operation.get("error_type") or "generation_failed",
                    "message": operation.get("error_message") or "Flow Music generation failed",
                })

        terminal_states = completed_states | failed_states
        all_terminal = len(operation_ids) >= settings.expected_clips and all(
            item["status"] in terminal_states for item in statuses
        )
        enough_clips = len(clip_ids) >= settings.expected_clips
        any_pending = any(item["status"] not in terminal_states for item in statuses)
        failed = all_terminal and not clip_ids and bool(errors)
        completed = enough_clips or (all_terminal and bool(clip_ids) and not any_pending)
        clips = [{
            "id": clip_id,
            "download_url": f"/api/jobs/{{job_id}}/download?clip_id={quote(clip_id, safe='')}&format=m4a",
            "wav_download_url": f"/api/jobs/{{job_id}}/download?clip_id={quote(clip_id, safe='')}&format=wav",
            "duration_s": duration_by_clip.get(clip_id),
        } for clip_id in clip_ids]
        return {
            "status": "failed" if failed else "completed" if completed else "pending",
            "operation_ids": operation_ids,
            "clip_ids": clip_ids,
            "progress": sum(progress_values) / len(progress_values) if progress_values else None,
            "clips": clips,
            "error": errors or None,
        }

    async def poll(
        self,
        provider_job_id: str,
        *,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        poll_timeout = settings.poll_timeout if timeout is None else timeout
        deadline = time.monotonic() + poll_timeout
        while time.monotonic() < deadline:
            result = await self.get_job(provider_job_id)
            if result["status"] in {"completed", "failed"}:
                return result
            await asyncio.sleep(settings.poll_interval)
        raise FlowMusicError(
            f"Flow Music generation did not finish within {poll_timeout:g}s",
            504,
        )

    async def download(self, clip_id: str, audio_format: str = "m4a") -> tuple[bytes, str]:
        if audio_format not in {"m4a", "wav"}:
            raise FlowMusicError("format must be m4a or wav", 400)
        data = await self._request(
            f"/__api/download/audio/{quote(clip_id, safe='')}?format={audio_format}",
            response_mode="base64",
            timeout=max(settings.request_timeout, 300),
        )
        if not isinstance(data, dict) or not data.get("base64"):
            raise FlowMusicError("Flow Music returned no audio data")
        try:
            content = base64.b64decode(data["base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise FlowMusicError("Flow Music returned invalid audio data") from exc
        content_type = data.get("contentType") or (
            "audio/wav" if audio_format == "wav" else "audio/mp4"
        )
        return content, content_type


client = FlowMusicClient()
