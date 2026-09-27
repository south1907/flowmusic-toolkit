"""FastAPI entry point for the unofficial standalone Flow Music service."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect

from app import __version__, db
from app.bridge import bridge
from app.config import settings
from app.flowmusic import FlowMusicError, client
from app.models import GenerateMusicRequest, MusicJobResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_db()
    yield


app = FastAPI(
    title="Unofficial Flow Music Local API",
    version=__version__,
    description="Generate music through the user's signed-in flowmusic.app browser session.",
    lifespan=lifespan,
)


def _raise(exc: FlowMusicError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _result_from_row(
    row: dict[str, Any],
    result: Optional[dict[str, Any]] = None,
    base_url: str = "",
) -> dict[str, Any]:
    payload = result
    if payload is None and row.get("result_json"):
        payload = json.loads(row["result_json"])
    payload = payload or {}
    clips = []
    for clip in payload.get("clips") or []:
        item = dict(clip)
        for field in ("download_url", "wav_download_url"):
            url = item.get(field, "").replace("{job_id}", row["id"])
            if base_url and url.startswith("/"):
                url = f"{base_url.rstrip('/')}{url}"
            item[field] = url
        clips.append(item)
    return {
        "id": row["id"],
        "status": payload.get("status") or row["status"],
        "project_id": row.get("project_id"),
        "clips": clips or None,
        "progress": payload.get("progress"),
        "error": payload.get("error") or row.get("error_message"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _stored_clip_count(row: dict[str, Any]) -> int:
    if not row.get("result_json"):
        return 0
    try:
        return len((json.loads(row["result_json"]) or {}).get("clips") or [])
    except (TypeError, ValueError):
        return 0


def _stored_conversation_id(row: dict[str, Any]) -> Optional[str]:
    if not row.get("result_json"):
        return None
    try:
        value = (json.loads(row["result_json"]) or {}).get("conversation_id")
        return value if isinstance(value, str) else None
    except (TypeError, ValueError):
        return None


async def _sync(
    row: dict[str, Any],
    result: dict[str, Any],
    base_url: str = "",
) -> dict[str, Any]:
    status = result.get("status", "pending")
    updated = await db.update_job(
        row["id"],
        status=status if status in {"pending", "completed", "failed"} else "pending",
        result=result,
        error_message=json.dumps(result.get("error"), ensure_ascii=False)
        if result.get("error")
        else None,
    )
    return _result_from_row(updated or row, result, base_url)


@app.get("/")
async def root():
    return {"name": app.title, "version": app.version, "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version, **bridge.status}


@app.get("/api/status")
async def status():
    return {
        "mode": "signed_in_browser_session",
        "token_required": False,
        "flowmusic_url": "https://www.flowmusic.app/",
        **bridge.status,
    }


@app.websocket("/ws/extension")
async def extension_socket(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    if origin and not (
        origin.startswith("chrome-extension://")
        or origin.startswith("http://127.0.0.1")
        or origin.startswith("http://localhost")
    ):
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    await websocket.accept()
    await bridge.attach(websocket)
    try:
        while True:
            await bridge.handle_message(await websocket.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        bridge.detach(websocket)


@app.post(
    "/api/generate",
    response_model=MusicJobResponse,
    status_code=202,
    responses={200: {"description": "Generation completed while waiting"}},
)
async def generate(body: GenerateMusicRequest, response: Response, request: Request):
    base_url = str(request.base_url).rstrip("/")
    try:
        remote = await client.generate(
            prompt=body.prompt,
        )
        row = await db.create_job(
            remote["provider_job_id"],
            remote.get("project_id"),
            body.model_dump(),
        )
        if body.wait:
            try:
                result = await client.poll(
                    remote["provider_job_id"],
                    project_id=remote.get("project_id"),
                    timeout=body.wait_timeout_s,
                )
            except FlowMusicError as exc:
                if exc.status_code not in {401, 403, 504}:
                    raise
                # Once Flow Music accepted the generation, a temporary auth
                # failure while polling must not make the create request look
                # failed. Return the local id so polling can resume later.
                response.status_code = 202
                return _result_from_row(row, remote, base_url)
            response.status_code = 200
            return await _sync(row, result, base_url)
        return _result_from_row(row, remote, base_url)
    except FlowMusicError as exc:
        _raise(exc)


@app.get("/api/jobs", response_model=list[MusicJobResponse])
async def jobs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    base_url = str(request.base_url).rstrip("/")
    return [_result_from_row(row, base_url=base_url) for row in await db.list_jobs(limit, offset)]


@app.get("/api/jobs/{job_id}", response_model=MusicJobResponse)
async def get_job(job_id: str, request: Request, refresh: bool = True):
    base_url = str(request.base_url).rstrip("/")
    row = await db.get_job(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    has_all_clips = _stored_clip_count(row) >= settings.expected_clips
    if not refresh or row["status"] == "failed" or (row["status"] == "completed" and has_all_clips):
        return _result_from_row(row, base_url=base_url)
    try:
        return await _sync(
            row,
            await client.get_job(
                row["provider_job_id"],
                project_id=row.get("project_id"),
                conversation_id=_stored_conversation_id(row),
            ),
            base_url,
        )
    except FlowMusicError as exc:
        _raise(exc)


@app.post("/api/jobs/{job_id}/poll", response_model=MusicJobResponse)
async def poll_job(
    job_id: str,
    request: Request,
    timeout_s: Optional[float] = Query(default=None, ge=10, le=3600),
):
    base_url = str(request.base_url).rstrip("/")
    row = await db.get_job(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    has_all_clips = _stored_clip_count(row) >= settings.expected_clips
    if row["status"] == "failed" or (row["status"] == "completed" and has_all_clips):
        return _result_from_row(row, base_url=base_url)
    try:
        return await _sync(
            row,
            await client.poll(
                row["provider_job_id"],
                project_id=row.get("project_id"),
                conversation_id=_stored_conversation_id(row),
                timeout=timeout_s,
            ),
            base_url,
        )
    except FlowMusicError as exc:
        _raise(exc)


@app.get("/api/jobs/{job_id}/download")
async def download(
    job_id: str,
    clip_id: Optional[str] = None,
    format: str = Query(default="m4a", pattern="^(m4a|wav)$"),
):
    row = await db.get_job(job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    result = json.loads(row["result_json"]) if row.get("result_json") else {}
    clips = result.get("clips") or []
    target = clip_id or (clips[0].get("id") if clips else None)
    if not target:
        raise HTTPException(409, "The job has no completed clip")
    try:
        content, content_type = await client.download(target, format)
    except FlowMusicError as exc:
        _raise(exc)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{target}.{format}"'},
    )


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        ws_max_size=64 * 1024 * 1024,
    )


if __name__ == "__main__":
    run()
