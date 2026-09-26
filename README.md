# Google Flow Music Local API

Project độc lập cung cấp REST API để tạo nhạc bằng chính account đang đăng
nhập tại [flowmusic.app](https://www.flowmusic.app/). Không cần
`FLOWMUSIC_API_TOKEN`, không nhập Google password vào server và không lưu cookie
trong SQLite.

> Flow Music hiện không công bố REST API ổn định cho luồng này. Project gọi các
> route web first-party ` /__api/... ` qua tab Chrome đang đăng nhập; khi Flow
> Music thay đổi frontend, adapter có thể cần cập nhật. Việc sử dụng account và
> credits vẫn tuân theo điều khoản của Flow Music.

## Kiến trúc

```text
API client -> FastAPI :8123 -> WebSocket -> Chrome extension
                                            |
                                            v
                              flowmusic.app tab đã đăng nhập
                                            |
                                            v
                              first-party /__api requests
```

- FastAPI chỉ gửi path, method và payload cho extension.
- Extension chạy `fetch` trong page context của `flowmusic.app`.
- Supabase session, cookie và bearer token chỉ được sử dụng bên trong tab; chúng
  không được gửi về Python.
- Job được lưu cục bộ tại `data/google-flow-music.db`.

## Cài đặt

Yêu cầu Python 3.9+ và Chrome/Chromium.

```bash
cd /Users/heva/Desktop/work/google-flow-music
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

API chạy tại `http://127.0.0.1:8123`; Swagger UI ở
`http://127.0.0.1:8123/docs`.

### Cài Chrome extension

1. Mở `chrome://extensions`.
2. Bật **Developer mode**.
3. Chọn **Load unpacked** và trỏ tới folder
   `/Users/heva/Desktop/work/google-flow-music/extension`.
4. Mở `https://www.flowmusic.app/` trong cùng Chrome profile và đăng nhập.
5. Bấm icon extension; cả **Local API** và **Flow Music tab** phải xanh.

Kiểm tra từ terminal:

```bash
curl http://127.0.0.1:8123/api/status
```

## Tạo nhạc

```bash
curl -X POST http://127.0.0.1:8123/api/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Create a song titled Mưa trên mái hiên. Vietnamese indie folk, acoustic guitar, soft female vocal, 82 bpm. Use these lyrics exactly:\n[Verse]\nMưa rơi trên mái hiên\n[Chorus]\nTa đi qua những ngày dịu êm"
  }'
```

API không có field `title`, `lyrics`, `instrumental` hay `project_id`. Flow Music
nhận một chuỗi hội thoại duy nhất, vì vậy mọi yêu cầu nội dung phải nằm trong
`prompt`, ví dụ:

```text
Create a song titled "Mưa trên mái hiên".
Style: Vietnamese indie folk, acoustic guitar, 82 bpm.
Instrumental only; no vocals.

Hoặc nếu có lời:
Use these lyrics exactly:
[Verse]
Mưa rơi trên mái hiên
```

Response trả `id` cục bộ. Poll job:

```bash
curl http://127.0.0.1:8123/api/jobs/JOB_ID
```

Flow Music mặc định tạo hai biến thể cho mỗi prompt. API chờ cả hai operation và
trả cả hai phần tử trong `clips`, mỗi phần tử có link M4A và WAV riêng.
Số lượng mong đợi mặc định là `FLOWMUSIC_EXPECTED_CLIPS=2` và có thể đổi qua
biến môi trường nếu hành vi của Flow Music thay đổi.

### Chờ hoàn thành ngay trong request tạo nhạc

Thêm `"wait": true` để `POST /api/generate` chỉ trả về sau khi Flow Music hoàn
thành. `wait_timeout_s` là tùy chọn, từ 10 đến 3600 giây; mặc định lấy từ
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

API trả HTTP `200` khi đã hoàn tất. Nếu hết thời gian chờ nhưng Flow Music vẫn
đang xử lý, API trả HTTP `202` cùng `id` và trạng thái `pending`; generation vẫn
tiếp tục và có thể kiểm tra lại bằng endpoint job.

Khi hoàn tất, `download_url` và `wav_download_url` là URL đầy đủ theo host của
request, ví dụ `http://127.0.0.1:8123/api/jobs/.../download?...`.

Với job đã tạo, có thể chờ đến khi hoàn thành bằng:

```bash
curl -X POST 'http://127.0.0.1:8123/api/jobs/JOB_ID/poll?timeout_s=1200'
```

Download clip đầu tiên:

```bash
curl 'http://127.0.0.1:8123/api/jobs/JOB_ID/download?format=m4a' -o song.m4a
curl 'http://127.0.0.1:8123/api/jobs/JOB_ID/download?format=wav' -o song.wav
```

Các endpoint chính:

- `GET /health`
- `GET /api/status`
- `POST /api/generate`
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `POST /api/jobs/{id}/poll`
- `GET /api/jobs/{id}/download?format=m4a|wav`

## Test

```bash
pip install -r requirements-dev.txt
pytest
node --check extension/background.js
```
