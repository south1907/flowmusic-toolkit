from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import db, main
from app.flowmusic import FlowMusicError


def test_stored_clip_count_handles_pending_job_without_result():
    assert main._stored_clip_count({"result_json": None}) == 0
    assert main._stored_clip_count({"result_json": '{"clips":[{"id":"clip-1"}]}'}) == 1


class CompletedClient:
    async def generate(self, **_):
        return {
            "provider_job_id": "provider-completed",
            "project_id": "project-1",
            "status": "pending",
        }

    async def poll(
        self, provider_job_id, *, project_id=None, conversation_id=None, timeout=None
    ):
        assert provider_job_id == "provider-completed"
        assert project_id == "project-1"
        assert timeout == 120
        return {
            "status": "completed",
            "progress": 100,
            "clips": [
                {
                    "id": "clip-1",
                    "download_url": "/api/jobs/{job_id}/download?clip_id=clip-1&format=m4a",
                    "wav_download_url": "/api/jobs/{job_id}/download?clip_id=clip-1&format=wav",
                }
            ],
        }


class SlowClient(CompletedClient):
    async def generate(self, **_):
        return {
            "provider_job_id": "provider-slow",
            "project_id": "project-1",
            "status": "pending",
        }

    async def poll(
        self, provider_job_id, *, project_id=None, conversation_id=None, timeout=None
    ):
        raise FlowMusicError("still running", 504)


class AuthRefreshClient(CompletedClient):
    async def generate(self, **_):
        return {
            "provider_job_id": "provider-auth-refresh",
            "project_id": "project-1",
            "status": "pending",
        }

    async def poll(
        self, provider_job_id, *, project_id=None, conversation_id=None, timeout=None
    ):
        raise FlowMusicError("temporary browser session refresh", 401)


def test_generate_wait_returns_completed_with_http_200(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "settings", SimpleNamespace(database_path=tmp_path / "completed.db"))
    monkeypatch.setattr(main, "client", CompletedClient())
    with TestClient(main.app) as api:
        response = api.post(
            "/api/generate",
            json={"prompt": "piano", "wait": True, "wait_timeout_s": 120},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["clips"][0]["id"] == "clip-1"
    assert response.json()["clips"][0]["download_url"].startswith("http://testserver/api/jobs/")
    assert response.json()["clips"][0]["wav_download_url"].startswith("http://testserver/api/jobs/")


def test_generate_wait_timeout_returns_pending_job_with_http_202(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "settings", SimpleNamespace(database_path=tmp_path / "pending.db"))
    monkeypatch.setattr(main, "client", SlowClient())
    with TestClient(main.app) as api:
        response = api.post(
            "/api/generate",
            json={"prompt": "piano", "wait": True, "wait_timeout_s": 120},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["id"]


def test_generate_wait_auth_refresh_returns_pending_job_with_http_202(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "settings", SimpleNamespace(database_path=tmp_path / "auth.db"))
    monkeypatch.setattr(main, "client", AuthRefreshClient())
    with TestClient(main.app) as api:
        response = api.post(
            "/api/generate",
            json={"prompt": "piano", "wait": True, "wait_timeout_s": 120},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["id"]


def test_generate_rejects_separate_content_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "settings", SimpleNamespace(database_path=tmp_path / "strict.db"))
    with TestClient(main.app) as api:
        response = api.post(
            "/api/generate",
            json={"prompt": "piano", "title": "Separate title is not supported"},
        )
    assert response.status_code == 422
