import pytest

from app.flowmusic import FlowMusicClient, FlowMusicError, parse_sse


class FakeBridge:
    def __init__(self):
        self.calls = []

    async def request(self, payload, timeout):
        self.calls.append((payload, timeout))
        path = payload["path"]
        if path == "/__api/projects":
            return {"status": 200, "data": {"id": "project-1"}}
        if path == "/__api/conversation":
            return {"status": 200, "data": {"job_id": "job-1"}}
        if "/stream?" in path:
            return {
                "status": 200,
                "data": (
                    'event: part\ndata: {"part":{"content":{"operation_id":"op-1"}}}\n\n'
                    'event: part\ndata: {"part":{"content":{"operation_id":"op-2"}}}\n\n'
                ),
            }
        if "audio-create-song-status" in path:
            clip_id = "clip-2" if path.endswith("op-2") else "clip-1"
            return {"status": 200, "data": {"status": "completed", "clip_id": clip_id}}
        raise AssertionError(path)


def test_parse_sse_extracts_ids():
    result = parse_sse(
        'event: conversation_id\ndata: {"id":"conversation-1"}\n\n'
        'event: part\ndata: {"part":{"content":{"operation_id":"op-1","clip_id":"clip-1"}}}\n\n'
        'event: part\ndata: {"part":{"content":{"operation_id":"op-2","clip_id":"clip-2"}}}\n\n'
    )
    assert result["conversation_id"] == "conversation-1"
    assert result["operation_ids"] == ["op-1", "op-2"]
    assert result["clip_ids"] == ["clip-1", "clip-2"]
    assert result["operations"] == [
        {"operation_id": "op-1", "clip_id": "clip-1"},
        {"operation_id": "op-2", "clip_id": "clip-2"},
    ]


def test_parse_sse_extracts_current_ab_result():
    result = parse_sse(
        'event: part\ndata: {"status":"final","part":{"part_kind":"tool-return",'
        '"content":{"operation_id":"op-a","clip_id":"clip-a",'
        '"operation_id_b":"op-b","clip_id_b":"clip-b",'
        '"a_b_test_id":"test-1"}}}\n\n'
    )
    assert result["operation_ids"] == ["op-a", "op-b"]
    assert result["clip_ids"] == ["clip-a", "clip-b"]
    assert result["operations"] == [
        {"operation_id": "op-a", "clip_id": "clip-a"},
        {"operation_id": "op-b", "clip_id": "clip-b"},
    ]


def test_parse_sse_treats_missing_stream_as_pending():
    result = parse_sse("Stream not found", "job-new")
    assert result["operation_ids"] == []
    assert result["clip_ids"] == []


def test_parse_sse_detects_final_stream():
    result = parse_sse(
        'event: part\ndata: {"part":{"content":{"operation_id":"op-1"}}}\n\n'
        "event: final\ndata: {}\n\n"
    )
    assert result["stream_complete"] is True


@pytest.mark.asyncio
async def test_get_job_completes_with_one_variant_when_stream_is_final():
    class SingleVariantBridge(FakeBridge):
        async def request(self, payload, timeout):
            if "/stream?" in payload["path"]:
                return {
                    "status": 200,
                    "data": (
                        'event: part\ndata: {"part":{"content":'
                        '{"operation_id":"op-1","clip_id":"clip-1"}}}\n\n'
                        "event: final\ndata: {}\n\n"
                    ),
                }
            return await super().request(payload, timeout)

    status = await FlowMusicClient(SingleVariantBridge()).get_job("job-single")
    assert status["status"] == "completed"
    assert [clip["id"] for clip in status["clips"]] == ["clip-1"]


@pytest.mark.asyncio
async def test_get_job_treats_missing_stream_as_pending():
    class MissingStreamBridge(FakeBridge):
        async def request(self, payload, timeout):
            if "/stream?" in payload["path"]:
                return {"status": 200, "data": "Stream not found"}
            return await super().request(payload, timeout)

    status = await FlowMusicClient(MissingStreamBridge()).get_job("job-new")
    assert status["status"] == "pending"
    assert status["clips"] == []


@pytest.mark.asyncio
async def test_get_job_recovers_completed_clips_from_project():
    class ProjectClipsBridge(FakeBridge):
        async def request(self, payload, timeout):
            path = payload["path"]
            if "/stream?" in path:
                return {"status": 200, "data": "Stream not found"}
            if path == "/__api/projects/project-1/clips/ids":
                return {"status": 200, "data": {"clip_ids": ["clip-a", "clip-b"]}}
            return await super().request(payload, timeout)

    status = await FlowMusicClient(ProjectClipsBridge()).get_job(
        "job-old", project_id="project-1"
    )
    assert status["status"] == "completed"
    assert [clip["id"] for clip in status["clips"]] == ["clip-a", "clip-b"]


@pytest.mark.asyncio
async def test_get_job_recovers_operations_from_project_transcript():
    class TranscriptBridge(FakeBridge):
        async def request(self, payload, timeout):
            path = payload["path"]
            if "/stream?" in path:
                return {"status": 200, "data": "Stream not found"}
            if path == "/__api/projects/project-1/clips/ids":
                return {"status": 200, "data": {"clip_ids": []}}
            if path == "/__api/projects/project-1/conversations/ids":
                return {"status": 200, "data": {"conversation_ids": ["conversation-1"]}}
            if path == "/__api/conversations/conversation-1/transcript":
                return {
                    "status": 200,
                    "data": {
                        "turns": [
                            {
                                "content": {
                                    "operation_id": "op-1",
                                    "clip_id": "clip-1",
                                    "operation_id_b": "op-2",
                                    "clip_id_b": "clip-2",
                                }
                            }
                        ]
                    },
                }
            return await super().request(payload, timeout)

    status = await FlowMusicClient(TranscriptBridge()).get_job(
        "job-old", project_id="project-1"
    )
    assert status["status"] == "completed"
    assert status["operation_ids"] == ["op-1", "op-2"]
    assert [clip["id"] for clip in status["clips"]] == ["clip-1", "clip-2"]


@pytest.mark.asyncio
async def test_generate_and_get_job():
    fake = FakeBridge()
    client = FlowMusicClient(fake)
    created = await client.generate(prompt='Create a song titled "Mưa". Vietnamese indie folk.')
    assert created["provider_job_id"] == "job-1"
    assert created["project_id"] == "project-1"
    project_body = fake.calls[0][0]["body"]
    assert project_body["title"].startswith("Create a song titled")
    conversation_body = fake.calls[1][0]["body"]
    assert conversation_body["parts"][0]["content"] == (
        'Create a song titled "Mưa". Vietnamese indie folk.'
    )
    status = await client.get_job("job-1")
    assert status["status"] == "completed"
    assert [clip["id"] for clip in status["clips"]] == ["clip-1", "clip-2"]
    waited = await client.poll("job-1", timeout=10)
    assert waited["status"] == "completed"


@pytest.mark.asyncio
async def test_poll_retries_temporary_auth_failure(monkeypatch):
    client = FlowMusicClient(FakeBridge())
    attempts = 0

    async def get_job(*_, **__):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FlowMusicError("refreshing browser session", 401)
        return {"status": "completed", "clips": []}

    async def no_sleep(_):
        return None

    monkeypatch.setattr(client, "get_job", get_job)
    monkeypatch.setattr("app.flowmusic.asyncio.sleep", no_sleep)

    result = await client.poll("job-1", timeout=10)
    assert result["status"] == "completed"
    assert attempts == 2


@pytest.mark.asyncio
async def test_rejects_unknown_private_path():
    client = FlowMusicClient(FakeBridge())
    with pytest.raises(FlowMusicError) as error:
        await client._request("/__api/not-allowed")
    assert error.value.status_code == 400
