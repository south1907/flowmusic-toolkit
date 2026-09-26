from types import SimpleNamespace

import pytest

from app import db


@pytest.mark.asyncio
async def test_job_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "settings", SimpleNamespace(database_path=tmp_path / "jobs.db"))
    await db.init_db()

    created = await db.create_job("provider-job-1", "project-1", {"prompt": "piano"})
    assert created["status"] == "pending"

    updated = await db.update_job(
        created["id"],
        status="completed",
        result={"status": "completed", "clips": [{"id": "clip-1"}]},
    )
    assert updated["status"] == "completed"
    assert (await db.get_job(created["id"]))["provider_job_id"] == "provider-job-1"
    assert len(await db.list_jobs()) == 1

