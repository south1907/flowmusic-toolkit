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


@pytest.mark.asyncio
async def test_generate_and_get_job():
    fake = FakeBridge()
    client = FlowMusicClient(fake)
    created = await client.generate(
        prompt='Create a song titled "Mưa". Vietnamese indie folk.'
    )
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
async def test_rejects_unknown_private_path():
    client = FlowMusicClient(FakeBridge())
    with pytest.raises(FlowMusicError) as error:
        await client._request("/__api/not-allowed")
    assert error.value.status_code == 400
