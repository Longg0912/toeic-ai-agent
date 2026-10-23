# TOEIC Tutor Agent

Đề tài: Xây dựng AI Agent gia sư cá nhân hóa
hỗ trợ học và luyện thi TOEIC.

## 1. Mục tiêu

Xây dựng hệ thống giúp học viên:

- Luyện tập TOEIC Part 5.
- Nhận kết quả chấm điểm tự động.
- Theo dõi tiến độ học tập.
- Xác định điểm mạnh và điểm yếu.
- Nhận gợi ý ôn tập cá nhân hóa.
- Hỏi đáp kiến thức với AI Tutor Agent.

Hệ thống sẽ được mở rộng sang Part 6 và Part 7
sau khi Part 5 hoạt động ổn định.

## 2. Công nghệ

- Python 3.12
- FastAPI
- Streamlit
- SQLite
- SQLAlchemy 2.x
- Alembic
- OpenAI Responses API
- ChromaDB
- Sentence Transformers
- Pytest

## 3. Cấu trúc thư mục

- backend/: Backend FastAPI.
- frontend/: Giao diện Streamlit.
- tests/: Kiểm thử tự động.
- scripts/: Công cụ hỗ trợ.
- data/raw/: Dữ liệu gốc.
- data/processed/: Dữ liệu đã xử lý.
- data/lessons/: Tài liệu học TOEIC.
- docs/: Tài liệu dự án.
- experiments/: Các thử nghiệm.

## 4. Cài đặt trên Windows

Yêu cầu:

- Python 3.11 trở lên
- Visual Studio Code
- PowerShell
- Git

Mở terminal tại:

D:\toeic-ai-agent

### Tạo môi trường ảo

```powershell
py -3.12 -m venv .venv
```

### Kích hoạt môi trường ảo

```powershell
.\.venv\Scripts\Activate.ps1
```

### Cài đặt thư viện

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Kiểm tra thư viện

```powershell
python -m pip check
```

## 5. Kiến trúc

Frontend Streamlit giao tiếp với Backend FastAPI.

Backend chịu trách nhiệm:

- Xác thực và phân quyền.
- Quản lý ngân hàng câu hỏi.
- Chấm điểm theo answer key.
- Theo dõi năng lực người học.
- Điều phối Tutor Agent.
- Quản lý dữ liệu và tài liệu.

LLM không quyết định đáp án chấm điểm chính thức.

## 6. Bảo mật

- Không commit API key.
- Không commit file .env.
- Không commit dữ liệu cá nhân.
- Không commit SQLite database.
- Phân quyền tài liệu theo từng người dùng.
- Kiểm tra dữ liệu trước khi đưa vào RAG.

## 7. Phạm vi hiện tại

Giai đoạn 01 gồm:

A. Project structure và configuration.
B. FastAPI và endpoint GET /health.
C. Streamlit kết nối API.
D. Pytest kiểm thử endpoint.

Các nhóm sẽ được triển khai lần lượt.

Chưa có database, RAG hoặc AI Agent.

## 8. Theo dõi tiến độ

Xem file:

docs/PROJECT_PROGRESS.md