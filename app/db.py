"""Small SQLite repository for local generation jobs."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import aiosqlite

from app.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS music_job (
    id              TEXT PRIMARY KEY,
    provider_job_id TEXT NOT NULL UNIQUE,
    project_id      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','completed','failed')),
    request_json    TEXT NOT NULL,
    result_json     TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_music_job_status ON music_job(status);
CREATE INDEX IF NOT EXISTS idx_music_job_created_at ON music_job(created_at DESC);
"""


async def init_db() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


def _row(row: Optional[aiosqlite.Row]) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


async def create_job(provider_job_id: str, project_id: Optional[str], request: dict[str, Any]) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO music_job (id,provider_job_id,project_id,request_json)
               VALUES (?,?,?,?)""",
            (job_id, provider_job_id, project_id, json.dumps(request, ensure_ascii=False)),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM music_job WHERE id = ?", (job_id,))
        return dict(await cursor.fetchone())


async def get_job(job_id: str) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM music_job WHERE id = ?", (job_id,))
        return _row(await cursor.fetchone())


async def list_jobs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM music_job ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def update_job(
    job_id: str,
    *,
    status: str,
    result: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """UPDATE music_job
               SET status = ?, result_json = ?, error_message = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error_message,
                job_id,
            ),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM music_job WHERE id = ?", (job_id,))
        return _row(await cursor.fetchone())

