# Hướng dẫn Deploy toàn bộ hệ thống

---

## Mục lục

1. [Backend → Railway](#1-backend--railway)
2. [Frontend-user → Vercel](#2-frontend-user--vercel)
3. [Frontend-admin (local) → kết nối Railway](#3-frontend-admin-local--kết-nối-railway)

---

## 1. Backend → Railway

### 1.1 Chuẩn bị (làm một lần duy nhất)

#### Tạo `.gitignore` trong thư mục `backend/`

```
venv/
.env
__pycache__/
*.pyc
*.pyo
storage/
.DS_Store
```

> **Quan trọng:** Tạo file này **trước** khi chạy `git add .`. Nếu lỡ add rồi, xem phần xử lý bên dưới.

#### Tạo `railway.toml` trong thư mục `backend/`

```toml
[deploy]
startCommand = "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

> Migration sẽ chạy tự động mỗi lần deploy. Nếu không có migration mới thì Alembic chỉ kiểm tra và bỏ qua, không ảnh hưởng gì.

#### Khởi tạo Alembic migration lần đầu

```bash
cd backend
venv\Scripts\activate          # Windows
alembic revision --autogenerate -m "initial"
alembic upgrade head           # kiểm tra local trước
```

> **Lưu ý:** Nếu gặp lỗi `FileNotFoundError: alembic\script.py.mako`, tạo file đó thủ công:
>
> Tạo file `alembic/script.py.mako` với nội dung:
> ```
> """${message}
>
> Revision ID: ${up_revision}
> Revises: ${down_revision | comma,n}
> Create Date: ${create_date}
>
> """
> from typing import Sequence, Union
> from alembic import op
> import sqlalchemy as sa
> ${imports if imports else ""}
>
> revision: str = ${repr(up_revision)}
> down_revision: Union[str, None] = ${repr(down_revision)}
> branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
> depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}
>
> def upgrade() -> None:
>     ${upgrades if upgrades else "pass"}
>
> def downgrade() -> None:
>     ${downgrades if downgrades else "pass"}
> ```
> Rồi chạy lại `alembic revision --autogenerate -m "initial"`.

> **Lưu ý 2:** Nếu migration tạo ra toàn `ALTER TABLE` / `DROP INDEX` thay vì `CREATE TABLE`, file đó không dùng được cho Railway (fresh DB). Thay toàn bộ nội dung hàm `upgrade()` bằng:
> ```python
> def upgrade() -> None:
>     from app.database import Base
>     bind = op.get_bind()
>     Base.metadata.create_all(bind=bind, checkfirst=True)
> ```
> Rồi chạy lại `alembic upgrade head`.

---

### 1.2 Push lên GitHub

```bash
cd backend

git init
git add .
git commit -m "initial backend"
git branch -M main

# Tạo repo mới trên github.com, rồi:
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

---

### 1.3 Deploy lên Railway (lần đầu)

#### Tạo project

1. Vào [railway.app](https://railway.app) → **New Project**
2. Chọn **Deploy from GitHub repo** → chọn repo vừa tạo
3. **Root Directory**: đặt là `backend`
4. Railway sẽ tự detect Python và dùng `railway.toml` để start

#### Thêm MySQL

1. Trong project canvas → click **+ New** (dấu cộng)
2. Chọn **Database** → **MySQL**
3. Đợi Railway tạo xong (xuất hiện card MySQL Online)

#### Thêm Volume (bắt buộc cho file audio)

> Tab **Volumes** không còn nằm trong service panel nữa. Phải thêm từ canvas.

1. Trong project canvas → click **+ New** (dấu cộng)
2. Chọn **Volume**
3. Mount Path: `/app/storage`
4. Chọn service gắn vào: **backend_listenPractice**
5. Volume này tồn tại vĩnh viễn, không bị xóa khi redeploy

#### Cấu hình biến môi trường

Click vào backend service → tab **Variables** → thêm lần lượt:

| Key | Value |
|---|---|
| `DB_HOST` | `${{MySQL.MYSQLHOST}}` |
| `DB_PORT` | `${{MySQL.MYSQLPORT}}` |
| `DB_NAME` | `${{MySQL.MYSQLDATABASE}}` |
| `DB_USER` | `${{MySQL.MYSQLUSER}}` |
| `DB_PASSWORD` | `${{MySQL.MYSQLPASSWORD}}` |
| `SECRET_KEY` | *(xem bên dưới)* |
| `STORAGE_PATH` | `/app/storage` |

> **Chú ý hay nhầm:**
> - `DB_NAME` → `${{MySQL.MYSQLDATABASE}}` (không phải hardcode tên DB local)
> - `DB_USER` → `${{MySQL.MYSQLUSER}}` (không phải `MYSQLDATABASE`)

**Tạo SECRET_KEY:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy output và dán vào ô `SECRET_KEY`. Giữ key này cố định — thay đổi sẽ làm mất hiệu lực tất cả JWT token (user bị logout).

Cú pháp `${{MySQL.MYSQLHOST}}` là Railway reference variable — tự lấy từ MySQL service, không cần copy thủ công.

#### Lấy public URL

Vào backend service → tab **Settings** → **Networking** → **Generate Domain**.
URL sẽ có dạng: `https://your-service.up.railway.app`

Lưu URL này lại, cần dùng cho các bước sau.

---

### 1.4 Khởi tạo database (lần đầu)

**Migration và tạo admin đều chạy tự động** khi Railway deploy lần đầu.

`app/main.py` có startup event tự seed admin nếu DB trống:

```python
@app.on_event("startup")
def seed_admin():
    from app.database import SessionLocal
    from app.modules.auth.model import User
    import bcrypt
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            pw = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
            db.add(User(username="admin", password_hash=pw, is_admin=True))
            db.commit()
    finally:
        db.close()
```

Sau khi Railway deploy xong, login bằng: `admin` / `admin123`

> Seed chỉ chạy khi bảng `users` trống hoàn toàn. Những lần redeploy sau không tạo lại.

---

### 1.5 Cập nhật code (quy trình thường ngày)

```bash
# Sửa code xong...
git add .
git commit -m "mô tả thay đổi"
git push origin main
```

Railway tự detect push và redeploy. Xem log tại tab **Deployments**.

---

### 1.6 Thay đổi database schema

Mỗi khi thêm/sửa model (ví dụ thêm column):

```bash
cd backend
venv\Scripts\activate

# 1. Tạo migration
alembic revision --autogenerate -m "mo_ta_thay_doi"

# 2. Kiểm tra file vừa tạo trong alembic/versions/
#    (đọc lại để chắc chắn đúng trước khi apply)

# 3. Commit + push
git add alembic/versions/
git commit -m "migration: mo_ta_thay_doi"
git push origin main
```

Railway tự redeploy và chạy `alembic upgrade head` tự động (đã cấu hình trong `railway.toml`). Không cần làm thêm bước nào.

---

### 1.7 Upload audio/SRT mới

Không liên quan đến GitHub. Dùng frontend-admin local để upload trực tiếp lên Railway:

1. Mở frontend-admin (đã cấu hình trỏ sang Railway — xem Phần 3)
2. Upload track như bình thường
3. File được lưu vào Railway Volume (`/app/storage`) — tồn tại vĩnh viễn

---

### 1.8 Cập nhật CORS (sau khi có domain frontend)

Mở `app/main.py`, thay `allow_origins=["*"]` thành:

```python
allow_origins=[
    "https://your-frontend-user.vercel.app",
    "https://your-custom-domain.com",  # nếu có
],
```

Commit + push như bình thường.

---

### 1.9 Theo dõi & debug

```bash
# Xem log real-time
railway logs

# Kiểm tra service còn sống
curl https://your-service.up.railway.app/api/health
```

> **Lưu ý:** `railway run <command>` chạy lệnh local với Railway env vars được inject, nhưng hostname `mysql.railway.internal` chỉ resolve được trong Railway network — không dùng được từ máy local. Để thực thi lệnh trực tiếp trên server, dùng Railway dashboard → tab **Deployments** → mở terminal (nếu plan hỗ trợ).

---

### Lưu ý Railway

- **Pricing**: Railway tính phí dựa trên resource dùng. Ước tính ~$5–10/tháng cho app nhỏ. Không có free tier cho production.
- **Redeploy thời gian**: ~1–2 phút mỗi lần push
- **Volume**: không bị tính vào redeploy, dữ liệu an toàn

---

## 2. Frontend-user → Vercel

### 2.1 Chuẩn bị (làm một lần)

#### Tạo `.gitignore` trong thư mục `frontend-user/`

```
node_modules/
dist/
.env.local
.DS_Store
```

> **Quan trọng:** Tạo file này **trước** khi chạy `git add .`.
> Nếu lỡ `git add .` trước khi có `.gitignore`, chạy lệnh sau để reset:
> ```bash
> git rm -r --cached .
> git add .
> git commit -m "initial frontend-user"
> ```

#### Tạo `src/vite-env.d.ts`

```typescript
/// <reference types="vite/client" />
```

File này cần có để TypeScript nhận biết `import.meta.env` — nếu thiếu sẽ báo lỗi `Property 'env' does not exist on type 'ImportMeta'`.

#### Cập nhật API client

Mở `frontend-user/src/api/client.ts`, thay `baseURL: ""` thành:

```typescript
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
});
```

#### Sửa audio URL trong PlayerPage

Mở `frontend-user/src/features/player/PlayerPage.tsx`, tìm dòng `setAudioUrl(token.url)` và thay bằng:

```typescript
const base = import.meta.env.VITE_API_URL ?? "";
setAudioUrl(base + token.url);
```

> **Lý do:** `token.url` là relative path (`/api/audio?...`). Trên localhost Vite proxy xử lý được, nhưng trên Vercel browser resolve về Vercel domain → audio không load được. Phải prepend Railway URL vào trước.

#### Tạo `vercel.json` trong thư mục `frontend-user/`

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

File này bắt buộc để React Router hoạt động đúng — nếu không, F5 hoặc truy cập trực tiếp URL sẽ bị 404.

#### Tạo `.env.production` trong thư mục `frontend-user/`

```
VITE_API_URL=https://your-service.up.railway.app
```

Thay `your-service` bằng Railway URL thực tế.

> File `.env.production` có thể commit lên git (không chứa secret). Hoặc dùng Vercel dashboard để set (an toàn hơn).

#### Kiểm tra build local

```bash
cd frontend-user
npm install
npm run build    # phải build thành công không có lỗi
```

---

### 2.2 Push lên GitHub

```bash
cd frontend-user

git init
git add .
git commit -m "initial frontend-user"
git branch -M main
git remote add origin https://github.com/<username>/<repo-frontend-user>.git
git push -u origin main
```

> Có thể dùng cùng repo với backend (monorepo) hoặc repo riêng. Nếu monorepo, Vercel cho phép chọn subdirectory.

---

### 2.3 Deploy lên Vercel (lần đầu)

1. Vào [vercel.com](https://vercel.com) → **Add New Project**
2. Import GitHub repo
3. **Root Directory**: `frontend-user`
4. **Framework**: Vite (Vercel tự detect)
5. **Build Command**: `npm run build`
6. **Output Directory**: `dist`
7. **Environment Variables**: thêm `VITE_API_URL` = `https://your-service.up.railway.app`
   (Nếu không dùng `.env.production`)
8. Click **Deploy**

---

### 2.4 Cập nhật code

```bash
git add .
git commit -m "mô tả thay đổi"
git push origin main
```

Vercel tự detect và redeploy. Xem log tại Vercel dashboard.

---

### Lưu ý Vercel

- **Free tier** rất rộng rãi cho SPA tĩnh, không lo hết quota
- **Redeploy**: ~30 giây
- **Preview deployments**: mỗi PR sẽ có URL preview riêng, tiện để test trước khi merge

---

## 3. Frontend-admin (local) → kết nối Railway

Frontend-admin **không deploy lên đâu**, chỉ chạy local. Nhưng cần trỏ sang Railway backend thay vì localhost.

### Những thay đổi cần làm trong project

#### 1. Cài thêm `@types/node`

```bash
cd frontend-admin
npm install --save-dev @types/node
```

Cần thiết để TypeScript nhận biết `process.cwd()` trong `vite.config.ts`.

#### 2. Cập nhật `frontend-admin/vite.config.ts`

Thay proxy target từ hardcode `localhost` sang đọc từ env variable:

```typescript
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      port: 3001,
      proxy: {
        "/api": {
          target: env.VITE_API_URL ?? "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
```

#### 3. Tạo `frontend-admin/.env.local`

```
VITE_API_URL=https://your-service.up.railway.app
```

Thay `your-service` bằng Railway URL thực tế (vào Railway → backend service → Settings → Networking → domain).

File `.env.local` **không commit lên git** (Vite tự bỏ qua file này).

Sau đó chạy:

```bash
cd frontend-admin
npm run dev
```

Tất cả request `/api/...` sẽ được proxy sang Railway thay vì localhost.

---

### Quy trình upload audio/SRT hàng ngày

```
Mở frontend-admin (npm run dev)
   ↓
Upload track mới qua giao diện
   ↓
Request đến: http://localhost:3001/api/admin/tracks
   ↓ (Vite proxy)
https://your-service.up.railway.app/api/admin/tracks
   ↓
Backend lưu file vào Railway Volume (/app/storage)
   ↓
Xong. Không cần push GitHub, không cần làm thêm gì.
```

---

## Tóm tắt checklist toàn bộ

### Backend
- [ ] Tạo `.gitignore` (exclude `venv/`, `.env`, `storage/`, `__pycache__/`)
- [ ] Tạo `railway.toml` với startCommand bao gồm `alembic upgrade head &&`
- [ ] Tạo `alembic/script.py.mako` (nếu chưa có)
- [ ] Tạo Alembic migration lần đầu (`alembic revision --autogenerate`)
- [ ] Kiểm tra nội dung migration — nếu không phải `CREATE TABLE` thì thay bằng `Base.metadata.create_all(checkfirst=True)`
- [ ] `git init` → `git add .` → `git commit` → `git branch -M main` → push GitHub
- [ ] Tạo Railway project, thêm MySQL service (+ New → Database → MySQL)
- [ ] Mount Volume tại `/app/storage` (+ New → Volume → chọn service)
- [ ] Set environment variables dùng reference variables (DB_HOST=`${{MySQL.MYSQLHOST}}`, v.v.)
- [ ] Generate domain (Settings → Networking)
- [ ] Tạo admin user qua public MySQL URL (xem mục 1.4)

### Frontend-user
- [ ] Tạo `.gitignore` (node_modules/, dist/) — **trước** `git add .`
- [ ] Tạo `src/vite-env.d.ts` với `/// <reference types="vite/client" />`
- [ ] Cập nhật `api/client.ts` dùng `import.meta.env.VITE_API_URL`
- [ ] Tạo `vercel.json` (SPA rewrite)
- [ ] Tạo `.env.production` với Railway URL
- [ ] `git init` → `git add .` → `git commit` → `git branch -M main` → push GitHub
- [ ] Deploy trên Vercel (Root Directory: `frontend-user`)

### Frontend-admin
- [ ] `npm install --save-dev @types/node`
- [ ] Cập nhật `vite.config.ts` dùng `loadEnv` + `env.VITE_API_URL`
- [ ] Tạo `.env.local` với `VITE_API_URL=https://your-service.up.railway.app`

### Sau khi có đủ domain
- [ ] Cập nhật CORS trong `app/main.py`
- [ ] Push + redeploy backend
