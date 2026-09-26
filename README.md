# Google Flow Music Local API

**English** | [Tiếng Việt](README.vi.md)

A standalone REST API that generates music with the account currently signed
in at [flowmusic.app](https://www.flowmusic.app/). It does not require a
`FLOWMUSIC_API_TOKEN`, ask for your Google password, or store browser cookies in
SQLite.

> Flow Music does not currently publish a stable REST API for this workflow.
> This project calls first-party `/__api/...` web routes through a signed-in
> Chrome tab. The adapter may need to be updated when the Flow Music frontend
> changes. Account and credit usage remain subject to the Flow Music terms.

## Architecture

```text
API client -> FastAPI :8123 -> WebSocket -> Chrome extension
                                            |
                                            v
                                  signed-in flowmusic.app tab
                                            |
                                            v
                                  first-party /__api requests
```

- FastAPI sends only the request path, method, and payload to the extension.
- The extension runs `fetch` in the `flowmusic.app` page context.
- The Supabase session, cookies, and bearer token are used only inside the tab;
  they are never sent to Python.
- Jobs are stored locally in `data/google-flow-music.db`.

## Installation

Python 3.9+ and Chrome/Chromium are required.

```bash
cd google-flow-music
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

The equivalent console command is also installed:

```bash
google-flow-music
```

The API runs at `http://127.0.0.1:8123`. Swagger UI is available at
`http://127.0.0.1:8123/docs`.

### Install the Chrome extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked** and choose this project's `extension/` directory.
4. Open `https://www.flowmusic.app/` in the same Chrome profile and sign in.
5. Select the extension icon. Both **Local API** and **Flow Music tab** should
   be green.

Check the connection from a terminal:

```bash
curl http://127.0.0.1:8123/api/status
```

## Generate music

```bash
curl -X POST http://127.0.0.1:8123/api/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Create a song titled Rain on the Window. Indie folk, acoustic guitar, soft female vocal, 82 bpm. Use these lyrics exactly:\n[Verse]\nRain falls on the window\n[Chorus]\nWe walk through gentler days"
  }'
```

The API does not accept separate `title`, `lyrics`, `instrumental`, or
`project_id` fields. Flow Music receives one conversation string, so all content
instructions belong in `prompt`, for example:

```text
Create a song titled "Rain on the Window".
Style: indie folk, acoustic guitar, 82 bpm.
Instrumental only; no vocals.

Or, for a song with lyrics:
Use these lyrics exactly:
[Verse]
Rain falls on the window
```

The response contains a local job `id`. Poll it with:

```bash
curl http://127.0.0.1:8123/api/jobs/JOB_ID
```

Flow Music normally creates two variants for each prompt. The API tracks both
operations and returns two entries in `clips`, each with separate M4A and WAV
download links. The expected count defaults to `FLOWMUSIC_EXPECTED_CLIPS=2` and
can be changed through the environment if Flow Music changes its behavior.

### Wait for completion in the generate request

Add `"wait": true` to keep `POST /api/generate` open until Flow Music finishes.
`wait_timeout_s` is optional, accepts 10–3600 seconds, and defaults to
`FLOWMUSIC_POLL_TIMEOUT`:

```bash
curl -X POST http://127.0.0.1:8123/api/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Create an instrumental cinematic ambient piano track. No vocals.",
    "wait": true,
    "wait_timeout_s": 1200
  }'
```

The API returns HTTP `200` when generation completes. If the wait limit expires
while Flow Music is still processing, it returns HTTP `202` with the local `id`
and `pending` status. Generation continues and can be checked through the job
endpoint.

Completed jobs contain absolute `download_url` and `wav_download_url` values
based on the request host, for example
`http://127.0.0.1:8123/api/jobs/.../download?...`.

To wait for an existing job:

```bash
curl -X POST 'http://127.0.0.1:8123/api/jobs/JOB_ID/poll?timeout_s=1200'
```

Download the first clip:

```bash
curl 'http://127.0.0.1:8123/api/jobs/JOB_ID/download?format=m4a' -o song.m4a
curl 'http://127.0.0.1:8123/api/jobs/JOB_ID/download?format=wav' -o song.wav
```

Main endpoints:

- `GET /health`
- `GET /api/status`
- `POST /api/generate`
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `POST /api/jobs/{id}/poll`
- `GET /api/jobs/{id}/download?format=m4a|wav`

## Testing and development

```bash
pip install -r requirements-dev.txt
make check
```

Development commands:

- `make install-dev` — create the virtual environment and install development
  dependencies.
- `make run` — start the API.
- `make format` — format Python and apply safe lint fixes.
- `make check` — lint Python/JavaScript, validate the extension manifest, and
  run the test suite.

## License

Released under the [MIT License](LICENSE).
