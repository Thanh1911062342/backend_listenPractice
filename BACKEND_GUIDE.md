# Backend Code Guide

Tài liệu này mô tả chi tiết cấu trúc, luồng hoạt động và từng file code trong backend.

---

## Mục lục

1. [Công nghệ sử dụng](#công-nghệ-sử-dụng)
2. [Folder structure](#folder-structure)
3. [Các flow chính](#các-flow-chính)
4. [Mô tả từng file](#mô-tả-từng-file)

---

## Công nghệ sử dụng

| Thư viện | Vai trò |
|---|---|
| **FastAPI** | Web framework — tự động sinh docs tại `/docs` |
| **SQLAlchemy 2.0 (sync)** | ORM — map Python class ↔ bảng DB |
| **PyMySQL** | Driver kết nối MySQL |
| **Alembic** | Migration — quản lý thay đổi schema DB |
| **Pydantic v2** | Validate request/response body |
| **bcrypt** | Hash password |
| **python-jose** | Tạo/verify JWT token |
| **pydantic-settings** | Đọc config từ `.env` |

---

## Folder structure

```
backend/
├── app/
│   ├── main.py              ← Điểm khởi động, khai báo app + middleware
│   ├── config.py            ← Đọc biến môi trường, khai báo settings
│   ├── database.py          ← Kết nối DB, tạo engine + session
│   │
│   └── modules/             ← Mỗi module = 1 tính năng độc lập
│       ├── auth/            ← Đăng ký / đăng nhập / JWT
│       ├── content/         ← Track, category, segment, audio
│       ├── exercise/        ← Tạo và format câu hỏi từ segment
│       └── session/         ← Session luyện tập + chấm điểm
│
├── alembic/                 ← Migration files
│   ├── env.py               ← Cấu hình alembic đọc DB từ settings
│   └── versions/            ← Từng file = 1 lần thay đổi schema
│
├── storage/                 ← File audio và SRT (không commit lên git)
│   ├── audio/
│   └── srt/
│
├── railway.toml             ← Cấu hình Railway: chạy migration rồi start server
├── requirements.txt
└── .env                     ← Biến môi trường (không commit)
```

### Cấu trúc bên trong mỗi module

Mỗi module đều có cùng pattern:

```
module/
├── model.py       ← SQLAlchemy ORM class (ánh xạ tới bảng DB)
├── schema.py      ← Pydantic class (validate input/output API)
├── repository.py  ← Truy vấn DB thuần túy (CRUD), không có business logic
├── service.py     ← Business logic, gọi repository
└── router.py      ← Định nghĩa API endpoints, gọi service
```

> **Tại sao tách như vậy?**
> - `repository` chỉ biết về DB. Muốn đổi sang PostgreSQL? Chỉ sửa repository.
> - `service` chứa logic nghiệp vụ, không quan tâm đến HTTP hay DB.
> - `router` chỉ nhận request, gọi service, trả response.
> - Mỗi tầng có trách nhiệm riêng → dễ đọc, dễ test, dễ sửa.

---

## Các flow chính

### Flow 1: Đăng nhập

```
POST /api/auth/login
  { username, password }
       │
       ▼
auth/router.py → service.login()
       │
       ├─ repository.get_by_username(db, username)
       │    └─ SELECT * FROM users WHERE username = ?
       │
       ├─ bcrypt.checkpw(password, user.password_hash)
       │    └─ Sai → 401 Invalid credentials
       │
       └─ create_access_token(user.id)
            └─ jwt.encode({ sub: user_id, exp: +7days }, SECRET_KEY)
                 └─ Trả về { access_token, token_type: "bearer" }
```

Token được lưu ở client (localStorage). Mọi request sau đó phải gửi:
```
Authorization: Bearer <token>
```

---

### Flow 2: Xác thực request (middleware)

```
Bất kỳ endpoint nào có Depends(get_current_user)
       │
       ▼
auth/dependencies.py → get_current_user()
       │
       ├─ Lấy token từ header Authorization
       ├─ jwt.decode(token, SECRET_KEY) → user_id
       ├─ repository.get_by_id(db, user_id) → User
       └─ Trả User object về cho endpoint

Nếu endpoint có Depends(require_admin):
       └─ Kiểm tra user.is_admin == True, nếu không → 403
```

---

### Flow 3: Load audio (bảo mật bằng signed URL)

Không cho client download audio trực tiếp vì URL sẽ bị share lại tự do.
Thay vào đó dùng token ngắn hạn (15 phút):

```
Bước 1 — Frontend gọi:
  GET /api/tracks/{track_id}/audio-token
       │
       ▼
content/security.py → create_audio_token(track_id, user_id)
       │
       ├─ exp = now + 900 (giây)
       ├─ sig = HMAC-SHA256("{track_id}:{user_id}:{exp}", SECRET_KEY)
       └─ Trả { url: "/api/audio?tid=...&uid=...&exp=...&sig=..." }

Bước 2 — Frontend set audio.src = baseURL + token.url

Bước 3 — Browser tự fetch:
  GET /api/audio?tid=1&uid=5&exp=1234567890&sig=abc...
       │
       ▼
content/router.py
       ├─ security.verify_audio_token() → kiểm tra sig và exp
       └─ FileResponse(audio_path)  ← stream file về browser
```

> **Tại sao cần HMAC signature?**
> Nếu chỉ dùng `exp` thì ai cũng có thể giả mạo URL với exp lớn tùy ý. HMAC đảm bảo chỉ server mới tạo được sig hợp lệ vì chỉ server biết `SECRET_KEY`.

---

### Flow 4: Tạo exercise (lazy creation)

Exercise không được tạo sẵn mà tạo khi cần lần đầu tiên:

```
GET /api/tracks/{track_id}/exercise?type=fill_blank
       │
       ▼
exercise/service.py → get_or_create(db, track_id, "fill_blank")
       │
       ├─ repository.get_by_track() → đã có exercise chưa?
       │    └─ Có rồi → trả về luôn
       │
       └─ Chưa có → tạo mới:
            ├─ content_repo.get_segments_by_track() → lấy tất cả segments
            ├─ repository.create_exercise() → tạo bảng ghi Exercise
            └─ Với mỗi segment → tạo ExerciseQuestion:
                 question_data = {
                   type: "fill_blank",
                   correct_text: segment.clean_text,
                   speaker: segment.speaker,
                   audio_start_ms, audio_end_ms
                 }
```

---

### Flow 5: Bắt đầu session và lấy câu hỏi

```
POST /api/sessions
  { exercise_id, lock_from_seq?, lock_to_seq? }
       │
       ▼
session/service.py → start()
       ├─ Tính locked_start, locked_end từ seq (1-indexed) → order (0-indexed)
       └─ repository.create() → INSERT user_sessions

GET /api/sessions/{session_id}/questions
       │
       ▼
session/service.py → all_questions()
       ├─ Xác định range [locked_start, locked_end]
       ├─ ex_repo.get_questions_in_range() → lấy ExerciseQuestion với JOIN segment
       └─ Với mỗi câu:
            exercise/service.py → format_question(q, order, total, session_seed)
                 ├─ Đọc q.segment.is_question
                 ├─ Nếu is_question=False → trả display_text = correct_text (đọc thôi)
                 └─ Nếu is_question=True:
                      seed = session_id XOR display_order  ← khác nhau mỗi session
                      make_blank_display(correct_text, seed) → (text_với_＿＿＿, đáp_án)
```

> **Tại sao dùng XOR seed?** Mỗi session sẽ có vị trí blank khác nhau trên cùng 1 câu, tránh user nhớ vị trí blank từ lần trước.

---

### Flow 6: Nộp bài và chấm điểm

```
POST /api/sessions/{session_id}/answers/batch
  { answers: [{ question_id, blank_answers: ["câu trả lời"] }] }
       │
       ▼
session/service.py → submit_batch()
       │
       └─ Với mỗi câu trả lời:
            _check(question, user_input, blank_answers, session_id)
                 │
                 ├─ _norm(text): chuẩn hóa Unicode NFKC + xóa dấu câu/whitespace
                 ├─ _fuzzy_match(user, correct, threshold=0.8):
                 │    └─ difflib.SequenceMatcher → ratio similarity
                 │         ≥ 0.8 → đúng; < 0.8 → sai
                 └─ Trả (is_correct, score, correct_text)

            repository.upsert_answer() → INSERT hoặc UPDATE session_answers
            └─ UniqueConstraint(session_id, question_id) → không duplicate

Kết quả trả về:
  { results: [...], all_correct: bool }
```

> **Fuzzy matching là gì?**
> So sánh gần đúng — user gõ "べんきょう" nhưng đáp án là "べんきょう。" vẫn được tính đúng vì similarity > 80%. Chuẩn hóa trước khi so sánh để loại bỏ sự khác biệt về dấu câu và whitespace toàn chữ.

---

### Flow 7: Upload track mới (admin)

```
POST /api/admin/tracks (multipart/form-data)
  { title, category_id, difficulty, audio_file, srt_file? }
       │
       ▼
content/service.py → upload_track()
       │
       ├─ Tạo tên file: {category_slug}_{safe_title}.mp3
       ├─ Lưu audio vào storage/audio/
       │
       ├─ Nếu có SRT file:
       │    ├─ parse_srt() → list[{seq, start_ms, end_ms, raw_text, clean_text, speaker}]
       │    └─ Lưu SRT vào storage/srt/
       │
       ├─ Nếu không có SRT:
       │    └─ stt/service.py → transcribe() bằng Whisper (tự động)
       │
       ├─ repository.create_track() → INSERT tracks
       └─ repository.bulk_create_segments() → INSERT nhiều segments 1 lần
```

---

### Flow 8: Parse SRT file

SRT là format phụ đề chuẩn, cấu trúc mỗi block:

```
1
00:00:01,200 --> 00:00:04,500
[1] こんにちは、田中さん。

2
00:00:05,000 --> 00:00:07,800
[2] あ、山田さん！元気ですか？
```

`content/service.py → parse_srt()`:
- Split theo dòng trắng → từng block
- Parse timestamp → milliseconds
- Regex `^\[(\d+)\]` → trích xuất speaker number
- `clean_text` = text sau khi bỏ `[speaker]` prefix
- `raw_text` = giữ nguyên `[speaker]` prefix

---

## Mô tả từng file

### `app/main.py`

Điểm khởi động của toàn bộ app.

- Tạo `FastAPI` instance
- Thêm `CORSMiddleware` — chỉ cho phép request từ domain Vercel và localhost
- Include 4 router với prefix `/api`
- `seed_admin()`: startup event chạy 1 lần — nếu bảng `users` trống thì tạo user `admin/admin123`

---

### `app/config.py`

Đọc config từ file `.env` và biến môi trường Railway.

```python
class Settings(BaseSettings):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD  # kết nối MySQL
    SECRET_KEY     # dùng cho JWT và HMAC audio token — giữ bí mật
    ALGORITHM      # "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES  # 7 ngày
    STORAGE_PATH   # đường dẫn thư mục lưu audio/SRT
```

`pydantic-settings` tự đọc từ `.env` hoặc biến môi trường hệ thống (Railway inject).

---

### `app/database.py`

Khởi tạo SQLAlchemy engine và session.

- `engine`: connection pool tới MySQL, `pool_pre_ping=True` để tự reconnect nếu bị ngắt
- `SessionLocal`: factory tạo DB session
- `Base`: class cha cho tất cả ORM model
- `get_db()`: generator dùng với FastAPI `Depends` — tự đóng session sau mỗi request

---

### `modules/auth/model.py`

Bảng `users`:

| Column | Kiểu | Ghi chú |
|---|---|---|
| `id` | int PK | |
| `username` | str unique | dùng để login |
| `email` | str nullable | optional |
| `password_hash` | str | bcrypt hash |
| `is_active` | bool | False = tài khoản bị khóa |
| `is_admin` | bool | quyền truy cập admin API |
| `created_at` | datetime | |
| `last_active_at` | datetime nullable | |

---

### `modules/auth/schema.py`

Pydantic schemas cho auth:
- `UserRegister`: `{ username, email?, password }` — input đăng ký
- `UserLogin`: `{ username, password }` — input đăng nhập
- `UserOut`: thông tin user trả về (không bao gồm password)
- `Token`: `{ access_token, token_type: "bearer" }` — response sau login/register

---

### `modules/auth/repository.py`

CRUD thuần cho bảng `users`:
- `get_by_id`, `get_by_username`, `get_by_email`: tìm user
- `create`: INSERT user mới

---

### `modules/auth/service.py`

Business logic xác thực:
- `hash_password(plain)`: bcrypt hash
- `verify_password(plain, hashed)`: so sánh bcrypt
- `create_access_token(user_id)`: tạo JWT với exp = +7 ngày
- `decode_token(token)`: verify JWT, trả `user_id`
- `register(db, data)`: kiểm tra trùng username/email → tạo user → trả token
- `login(db, username, password)`: verify password → trả token

---

### `modules/auth/dependencies.py`

FastAPI dependency injection cho auth:
- `get_current_user`: parse `Authorization: Bearer <token>` → trả `User` object
- `require_admin`: gọi `get_current_user` rồi kiểm tra `is_admin`

Dùng trong router: `Depends(get_current_user)` hoặc `Depends(require_admin)`.

---

### `modules/content/model.py`

**Bảng `categories`**: nhóm các track theo loại học (JLPT, hội thoại, podcast...)

| Column | Ghi chú |
|---|---|
| `slug` | unique, dùng làm tên thư mục file |
| `type` | enum: jlpt / kaiwa / podcast / general |
| `display_order` | thứ tự hiển thị |

**Bảng `tracks`**: một file audio học tiếng Nhật

| Column | Ghi chú |
|---|---|
| `audio_filename` | tên file trong `storage/audio/` |
| `srt_filename` | tên file trong `storage/srt/` |
| `duration_ms` | độ dài audio tính bằng milliseconds |
| `updated_at` | dùng để invalidate cache audio ở frontend |

**Bảng `segments`**: một đoạn thoại trong track (1 block SRT = 1 segment)

| Column | Ghi chú |
|---|---|
| `seq` | số thứ tự (bắt đầu từ 1, theo SRT) |
| `start_ms`, `end_ms` | thời gian trong audio |
| `raw_text` | text gốc kể cả `[speaker]` prefix |
| `clean_text` | text sạch, dùng làm đáp án |
| `speaker` | số thứ tự người nói (lấy từ `[1]`, `[2]`...) |
| `is_question` | False → hiện full text, không cần điền vào chỗ trống |

---

### `modules/content/schema.py`

- `TrackOut`: thông tin track trả về user (bao gồm `updated_at` cho cache invalidation)
- `TrackDetail`: TrackOut + danh sách segments
- `AdminSegmentOut`: thông tin segment cho admin (bao gồm `is_question`, `raw_text`)
- `SegmentPatch`: `{ is_question }` — body khi toggle câu hỏi
- `CategoryWithTracks`: category kèm danh sách tracks

---

### `modules/content/repository.py`

CRUD cho category, track, segment:
- `get_track_by_filename`: kiểm tra trùng tên file khi upload
- `bulk_create_segments`: INSERT nhiều segment 1 lần (hiệu quả hơn loop)
- `delete_segments_by_track`: xóa hàng loạt khi re-upload SRT
- `update_segment_is_question`: toggle is_question cho 1 segment

---

### `modules/content/service.py`

Business logic xử lý nội dung:

**`parse_srt(content)`**: parse chuỗi SRT thành list dict. Xử lý speaker prefix `[n]`.

**`_make_base_name(category_slug, title)`**: tạo tên file `{slug}_{safe_title}` (thay ký tự đặc biệt bằng `_`).

**`upload_track(...)`**: flow upload track mới — lưu file, parse/transcribe, tạo DB records.

**`update_track_files(db, track, audio_file, srt_file)`**: thay file cho track đã có:
- Audio: overwrite file cũ (đổi ext nếu cần)
- SRT: parse lại → xóa segments + exercises cũ → tạo mới
- Luôn touch `updated_at` để frontend biết cần clear cache

**`retranscribe_track(...)`**: chạy lại Whisper trên audio hiện có → replace toàn bộ segments.

**`_clear_track_exercise_data(db, track_id)`**: xóa cascade exercises → sessions → answers. Gọi trước khi thay segments vì ExerciseQuestion trỏ vào segment cũ.

---

### `modules/content/security.py`

HMAC-SHA256 signed URL cho audio:
- `create_audio_token(track_id, user_id)`: tạo URL với TTL 15 phút
- `verify_audio_token(...)`: kiểm tra chưa hết hạn và signature hợp lệ
- `_sign(track_id, user_id, exp)`: tính HMAC — dùng `hmac.compare_digest` để tránh timing attack

---

### `modules/exercise/model.py`

**Bảng `exercises`**: một bộ câu hỏi gắn với một track

| Column | Ghi chú |
|---|---|
| `type` | fill_blank hoặc dictation |
| `config` | JSON, dự phòng mở rộng sau |

**Bảng `exercise_questions`**: một câu hỏi cụ thể

| Column | Ghi chú |
|---|---|
| `segment_id` | FK → segment (để đọc `is_question`) |
| `display_order` | thứ tự hiển thị (0-indexed) |
| `question_data` | JSON chứa correct_text, speaker, timestamp, type |

`question_data` format (fill_blank):
```json
{
  "type": "fill_blank",
  "correct_text": "こんにちは田中さん",
  "speaker": "1",
  "audio_start_ms": 1200,
  "audio_end_ms": 4500
}
```

---

### `modules/exercise/service.py`

**`make_blank_display(text, seed)`**: tạo câu có chỗ trống `＿＿＿`:
- Tìm tất cả chuỗi kanji/kana liên tiếp dài ≥ 2 ký tự
- Chọn ngẫu nhiên (theo seed) một vùng liên tiếp chiếm 30–70% ký tự Nhật
- Luôn giữ ≥ 1 cụm từ visible bên ngoài blank để có context
- Deterministic: cùng `(text, seed)` → luôn cùng kết quả

**`get_or_create(db, track_id, ex_type)`**: tạo exercise nếu chưa có (lazy creation).

**`format_question(q, order, total, session_seed)`**: chuẩn bị dict trả về cho frontend:
- Đọc `q.segment.is_question` (joinedload từ DB)
- Nếu `is_question=False`: trả `display_text = correct_text` (đọc thôi)
- Nếu `is_question=True`: gọi `make_blank_display(correct_text, session_id XOR display_order)`

---

### `modules/session/model.py`

**Bảng `user_sessions`**: một lần luyện tập

| Column | Ghi chú |
|---|---|
| `current_order` | câu đang làm (0-indexed) |
| `locked_start`, `locked_end` | giới hạn segment (NULL = toàn bộ) |
| `status` | in_progress / completed |

**Bảng `session_answers`**: câu trả lời của 1 lần luyện tập

| Column | Ghi chú |
|---|---|
| `user_input` | JSON string của `blank_answers` |
| `score` | float 0.0–1.0 |
| `UniqueConstraint(session_id, question_id)` | không được submit 2 lần cùng câu |

---

### `modules/session/schema.py`

- `SessionCreate`: `{ exercise_id, lock_from_seq?, lock_to_seq? }`
- `SessionOut`: thông tin session trả về (bao gồm locked_start/end)
- `BatchAnswerItem`: `{ question_id, blank_answers: [str] }`
- `BatchSubmit`: `{ answers: [BatchAnswerItem] }`
- `BatchResult` + `QuestionResult`: kết quả chấm điểm

---

### `modules/session/repository.py`

- `create(...)`: tạo session mới
- `upsert_answer(...)`: INSERT hoặc UPDATE câu trả lời (idempotent — submit nhiều lần không lỗi)
- `complete_session(...)`: set `status = completed`

---

### `modules/session/service.py`

**`_norm(text)`**: chuẩn hóa Unicode NFKC + strip dấu câu/whitespace tiếng Nhật trước khi so sánh.

**`_fuzzy_match(user, correct, threshold)`**: dùng `difflib.SequenceMatcher` tính tỷ lệ giống nhau:
- dictation: threshold 0.75 (khoan dung hơn)
- fill_blank: threshold 0.80

**`_check(q, user_input, blank_answers, session_id)`**: chấm điểm 1 câu:
- dictation: so sánh `user_input` với `correct_text`
- fill_blank (format mới): tái tạo `correct_answer` bằng cùng seed, so sánh với `blank_answers[0]`

**`_effective_range(session, total)`**: tính `[start, end]` order index thực tế (áp dụng locked range).

**`start(...)`**: tạo session, convert `lock_from_seq`/`lock_to_seq` (1-indexed) sang order (0-indexed).

**`all_questions(...)`**: lấy toàn bộ câu hỏi trong range, format cho frontend.

**`submit_batch(...)`**: chấm điểm hàng loạt + lưu kết quả vào DB.

---

## Lưu ý khi đọc code

**Dependency Injection pattern của FastAPI:**
```python
def my_endpoint(
    db: Session = Depends(get_db),           # tự inject DB session
    user: User = Depends(get_current_user),  # tự inject user đã auth
):
```
FastAPI tự gọi `get_db()` và `get_current_user()` trước khi chạy endpoint.

**`Depends` chain:** `require_admin` gọi `get_current_user` nội bộ → chỉ cần `Depends(require_admin)` là đủ, không cần cả 2.

**`response_model`:** FastAPI tự serialize output theo Pydantic schema — chỉ trả field được khai báo, field thừa bị bỏ qua.

**`server_default` vs `default`:** `server_default=func.now()` → MySQL tự điền khi INSERT. `default=True` trong SQLAlchemy → Python điền trước khi INSERT. Kết quả giống nhau nhưng cách thực hiện khác.
