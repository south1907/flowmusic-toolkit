# Unofficial Flow Music Local API

[English](README.md) | **Tiếng Việt**

[![CI](https://github.com/south1907/flowmusic-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/south1907/flowmusic-toolkit/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Project độc lập cung cấp REST API để tạo nhạc bằng chính tài khoản đang đăng
nhập tại [flowmusic.app](https://www.flowmusic.app/). Không cần
`FLOWMUSIC_API_TOKEN`, không nhập mật khẩu Google vào server và không lưu cookie
trong SQLite.

> **Dự án không chính thức:** Project không liên kết, không được xác nhận hay
> tài trợ bởi Google hoặc Flow Music. Project không cung cấp hoặc bán lại tài
> khoản, credits hay quyền truy cập Flow Music. Xem [Tuyên bố miễn trừ](DISCLAIMER.md)
> và [Chính sách riêng tư](PRIVACY.md).

> Flow Music hiện không công bố REST API ổn định cho luồng này. Project gọi các
> route web first-party `/__api/...` qua tab Chrome đang đăng nhập; khi Flow
> Music thay đổi frontend, adapter có thể cần cập nhật. Việc sử dụng tài khoản
> và credits vẫn tuân theo điều khoản của Flow Music.

## Tính năng

- API tạo nhạc chỉ cần prompt, có tùy chọn chờ đồng bộ.
- Theo dõi một hoặc hai biến thể của Flow Music và trả link M4A/WAV đầy đủ.
- Dùng tài khoản và credits từ Chrome session đã đăng nhập.
- Giữ thông tin xác thực bên trong page context của Flow Music.
- Lưu trạng thái generation cục bộ bằng SQLite.
- Có OpenAPI docs, tests, lint và GitHub CI workflow.

## Kiến trúc

```text
API client -> FastAPI :8123 -> WebSocket -> Chrome extension
                                            |
                                            v
                              tab flowmusic.app đã đăng nhập
                                            |
                                            v
                              first-party /__api requests
```

- FastAPI chỉ gửi path, method và payload cho extension.
- Extension chạy `fetch` trong page context của `flowmusic.app`.
- Supabase session, cookie và bearer token chỉ được sử dụng bên trong tab;
  chúng không được gửi về Python.
- Job được lưu cục bộ tại `data/google-flow-music.db`.

## Khởi động nhanh

Yêu cầu Python 3.9+ và Chrome/Chromium.

```bash
git clone https://github.com/south1907/flowmusic-toolkit.git
cd flowmusic-toolkit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

Trên Windows PowerShell, kích hoạt môi trường bằng:

```powershell
.venv\Scripts\Activate.ps1
```

Sau khi cài đặt, có thể dùng console command tương đương:

```bash
google-flow-music
```

API chạy tại `http://127.0.0.1:8123`; Swagger UI ở
`http://127.0.0.1:8123/docs`.

### Cài Chrome extension

1. Mở `chrome://extensions`.
2. Bật **Developer mode**.
3. Chọn **Load unpacked** và trỏ tới folder `extension/` của project.
4. Mở `https://www.flowmusic.app/` trong cùng Chrome profile và đăng nhập.
5. Bấm icon extension; cả **Local API** và **Flow Music tab** phải xanh.

Kiểm tra từ terminal:

```bash
curl http://127.0.0.1:8123/api/status
```

## Cấu hình

Project đọc cấu hình từ các biến môi trường:

| Biến | Mặc định | Mô tả |
|---|---:|---|
| `HOST` | `127.0.0.1` | Địa chỉ bind của API |
| `PORT` | `8123` | Port API và WebSocket của extension |
| `DATABASE_PATH` | `data/google-flow-music.db` | Database SQLite cục bộ |
| `FLOWMUSIC_REQUEST_TIMEOUT` | `90` | Timeout request trình duyệt, tính bằng giây |
| `FLOWMUSIC_POLL_INTERVAL` | `5` | Khoảng cách giữa các lần kiểm tra trạng thái |
| `FLOWMUSIC_POLL_TIMEOUT` | `900` | Thời gian chờ đồng bộ tối đa mặc định |
| `FLOWMUSIC_AUTH_RETRY_LIMIT` | `3` | Số lần retry refresh xác thực liên tiếp khi poll |
| `FLOWMUSIC_EXPECTED_CLIPS` | `2` | Số biến thể tối đa dùng để hoàn tất sớm |

Chrome extension hiện kết nối tới port `8123`. Nếu đổi `PORT`, cần cập nhật cả
`AGENT_WS_URL` và localhost permission trong folder `extension/`.

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

Flow Music thường tạo tối đa hai biến thể cho mỗi prompt, nhưng một số request
chỉ tạo một bản. API trả mọi biến thể đã tạo trong `clips`, mỗi phần tử có link
M4A và WAV riêng. Job hoàn tất sớm khi đủ số bản kỳ vọng, hoặc khi Flow Music đã
finalize stream và mọi operation nhận được đều kết thúc.
`FLOWMUSIC_EXPECTED_CLIPS` mặc định là `2`.

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

Tải clip đầu tiên:

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

## Xử lý lỗi xác thực

Khi Flow Music trả về `401` hoặc `403`, bridge sẽ reload tab Flow Music đã đăng
nhập một lần để ứng dụng first-party refresh access token, sau đó tự retry
request. Nếu lần retry vẫn không được xác thực, hãy mở tab đó và đăng nhập lại;
refresh session đã hết hạn hoặc bị thu hồi.

Nếu Flow Music đã chấp nhận yêu cầu tạo nhạc, lỗi xác thực tạm thời trong lúc
chờ đồng bộ sẽ trả job đã lưu dưới dạng `202 pending` thay vì làm request tạo
nhạc thất bại. Tiếp tục bằng `GET /api/jobs/{id}` hoặc
`POST /api/jobs/{id}/poll`.

## Kiểm tra và phát triển

```bash
pip install -r requirements-dev.txt
make check
```

Các lệnh phát triển:

- `make install-dev` — tạo virtualenv và cài project cùng dev tools.
- `make run` — chạy API.
- `make format` — format và tự sửa lint an toàn.
- `make check` — chạy lint JavaScript/Python, kiểm tra manifest và toàn bộ test.

## Thiết lập repository GitHub

Repository đã có issue forms, pull-request template, Dependabot và CI matrix cho
Python. Để đồng bộ các topics và labels được đề xuất lên GitHub:

```bash
gh auth login
make github-setup
```

Đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi mở pull request.

## Sử dụng có trách nhiệm

Chỉ sử dụng project với tài khoản mà bạn có quyền sử dụng và tuân thủ các điều
khoản, chính sách, giới hạn của Google/Flow Music cùng pháp luật áp dụng.

- Không bán lại, chia sẻ, cấp phép lại hoặc cung cấp quyền truy cập Flow Music
  cho bên thứ ba thông qua project này.
- Không vượt qua quota, rate limit, CAPTCHA, hệ thống an toàn, kiểm soát truy
  cập hoặc biện pháp bảo vệ khác.
- Không account farming và không tự động hóa hoạt động lạm dụng, lừa đảo hoặc
  trái pháp luật.
- Bảo đảm bạn có đầy đủ quyền đối với prompt, lời bài hát, tài liệu tham chiếu,
  nhạc được tạo và mọi nội dung được xuất bản hoặc phân phối.
- Công bố nội dung do AI tạo khi cần thiết; không tạo ấn tượng rằng project hay
  kết quả của nó được Google chính thức cung cấp hoặc xác nhận.
- Chỉ chạy API trên máy cục bộ đáng tin cậy và theo dõi credits của tài khoản.

Bạn tự chịu trách nhiệm hoàn toàn đối với tài khoản, credits, prompt, nội dung
được tạo, file tải xuống và cách sử dụng nhạc. Hãy đọc đầy đủ
[Tuyên bố miễn trừ](DISCLAIMER.md), [Chính sách riêng tư](PRIVACY.md),
[Điều khoản dịch vụ Google](https://policies.google.com/terms) và
[Chính sách về hành vi bị cấm khi sử dụng AI tạo sinh](https://policies.google.com/terms/generative-ai/use-policy)
trước khi sử dụng.

## Giấy phép

Phát hành theo [MIT License](LICENSE). Giấy phép chỉ áp dụng cho mã nguồn trong
repository này; không cấp quyền đối với dịch vụ, giao diện, thương hiệu, tài
khoản, credits của Google/Flow Music hoặc nội dung của bên thứ ba.
