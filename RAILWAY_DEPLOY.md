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

> **Quan trọng:** `storage/` chứa file audio — không commit lên GitHub. File sẽ được lưu trên Railway Volume.

#### Tạo `railway.toml` trong thư mục `backend/`

```toml
[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

#### Khởi tạo Alembic migration lần đầu

```bash
cd backend
venv\Scripts\activate          # Windows
alembic revision --autogenerate -m "initial"
alembic upgrade head           # kiểm tra local trước
```

---

### 1.2 Push lên GitHub

```bash
cd backend

git init
git add .
git commit -m "initial backend"

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

1. Trong project → **+ Add Service** → **Database** → **MySQL**
2. Đợi Railway tạo xong

#### Thêm Volume (bắt buộc cho file audio)

1. Click vào backend service → tab **Volumes**
2. **Add Volume** → Mount Path: `/app/storage`
3. Volume này tồn tại vĩnh viễn, không bị xóa khi redeploy

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

Cài Railway CLI:

```bash
npm install -g @railway/cli
railway login
railway link    # chọn project và service backend
```

Chạy migration:

```bash
cd backend
railway run alembic upgrade head
```

Tạo tài khoản admin đầu tiên:

```bash
railway run python -c "
from app.database import SessionLocal
from app.modules.auth.model import User
import bcrypt

db = SessionLocal()
pw = bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode()
u = User(email='admin@example.com', hashed_password=pw, is_admin=True)
db.add(u)
db.commit()
print('Admin created')
"
```

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

# 4. Sau khi Railway redeploy xong, apply migration
railway run alembic upgrade head
```

> Railway **không tự chạy migration**. Phải làm thủ công bước 4 sau mỗi push có schema change.

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

# Chạy lệnh trực tiếp trên server
railway run python -c "..."

# Kiểm tra service còn sống
curl https://your-service.up.railway.app/api/health
```

---

### Lưu ý Railway

- **Pricing**: Railway tính phí dựa trên resource dùng. Ước tính ~$5–10/tháng cho app nhỏ. Không có free tier cho production.
- **Redeploy thời gian**: ~1–2 phút mỗi lần push
- **Volume**: không bị tính vào redeploy, dữ liệu an toàn

---

## 2. Frontend-user → Vercel

### 2.1 Chuẩn bị (làm một lần)

#### Cập nhật API client để nhận env variable

Mở `frontend-user/src/api/client.ts`, thay `baseURL: ""` thành:

```typescript
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
});
```

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

#### 1. Cập nhật `frontend-admin/vite.config.ts`

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

#### 2. Tạo `frontend-admin/.env.local`

```
VITE_API_URL=https://your-service.up.railway.app
```

File `.env.local` **không commit lên git** (Vite tự bỏ qua file này).

Vậy là đủ. Sau đó chạy:

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
- [ ] Tạo `railway.toml` với startCommand
- [ ] Tạo Alembic migration lần đầu
- [ ] Push lên GitHub
- [ ] Tạo Railway project, thêm MySQL service
- [ ] Mount Volume tại `/app/storage`
- [ ] Set environment variables (dùng reference variable cho DB)
- [ ] Generate domain
- [ ] `railway run alembic upgrade head`
- [ ] Tạo admin user

### Frontend-user
- [ ] Cập nhật `api/client.ts` dùng `VITE_API_URL`
- [ ] Tạo `vercel.json` (SPA rewrite)
- [ ] Set `VITE_API_URL` (env.production hoặc Vercel dashboard)
- [ ] Push lên GitHub
- [ ] Deploy trên Vercel

### Frontend-admin
- [ ] Cập nhật `vite.config.ts` dùng `env.VITE_API_URL`
- [ ] Tạo `.env.local` với Railway URL

### Sau khi có đủ domain
- [ ] Cập nhật CORS trong `app/main.py`
- [ ] Push + redeploy backend
