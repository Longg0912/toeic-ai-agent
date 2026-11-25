# TOEIC Tutor Agent

**Đề tài:** Xây dựng AI Agent gia sư cá nhân hóa hỗ trợ học và luyện thi TOEIC.

## 1. Giới thiệu

TOEIC Tutor Agent là hệ thống hỗ trợ người học luyện thi TOEIC Reading, theo dõi năng lực và nhận hướng dẫn học tập cá nhân hóa từ AI Tutor Agent.

Dự án hướng tới việc kết hợp ngân hàng câu hỏi, mô hình hóa năng lực người học, hệ thống gợi ý học tập thích ứng và truy xuất tài liệu (RAG).

## 2. Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.12 |
| Backend | FastAPI |
| Frontend | Streamlit |
| Database | SQLite |
| ORM | SQLAlchemy 2.x |
| Database migration | Alembic |
| AI Tutor | Google Gemini API (`google-genai`) |
| RAG Vector Database | ChromaDB |
| Embedding | Sentence Transformers |
| Testing | Pytest |

## 3. Kiến trúc tổng quan

Frontend Streamlit giao tiếp với Backend FastAPI thông qua API.

Backend đảm nhiệm:

- Authentication và Authorization.
- Quản lý người dùng và hồ sơ học viên.
- Quản lý ngân hàng câu hỏi TOEIC.
- Quản lý phiên luyện tập và kết quả làm bài.
- Chấm điểm dựa trên answer key.
- Theo dõi năng lực và tiến độ học tập.
- Lập kế hoạch học tập thích ứng.
- Điều phối AI Tutor Agent.
- Quản lý tài liệu và truy xuất tri thức bằng RAG.

Gemini được sử dụng cho chức năng AI Tutor và các tác vụ hỗ trợ học tập. LLM không quyết định đáp án chấm điểm chính thức; kết quả chấm điểm dựa trên answer key do hệ thống quản lý.

## 4. Chức năng và phạm vi

### 4.1. Authentication và Authorization

- Đăng ký và đăng nhập.
- Xác thực bằng JWT Bearer Token.
- Quản lý phiên đăng nhập trên Streamlit.
- Role-based access control.
- Kiểm tra quyền sở hữu tài nguyên.

### 4.2. TOEIC Practice

Phạm vi sản phẩm Reading mục tiêu:

- Reading Practice Mode: luyện từng Part.
- Full Test Mode: bài thi Reading Part 5–7, gồm 100 câu trong 75 phút.
- Chấm điểm dựa trên answer key.
- Theo dõi kết quả luyện tập.

Nguồn nội dung dự kiến kết hợp:
- Question Bank hiện có.
- Nội dung do người dùng hoặc nhóm dự án biên soạn.
- Câu hỏi và bài đọc do AI tạo, cần được kiểm duyệt trước khi đưa vào ngân hàng đề chính thức.

### 4.3. AI Tutor Agent

- Hỏi đáp kiến thức TOEIC.
- Sử dụng Gemini API và function calling.
- Hỗ trợ truy xuất tài liệu qua RAG.
- Hỗ trợ giải thích nội dung câu hỏi và bài đọc.
- Hỗ trợ chọn văn bản trong bài luyện tập rồi gửi ngữ cảnh cho AI giải thích.

### 4.4. Student Modeling và Adaptive Recommendation

Theo dõi năng lực người học và sử dụng thông tin học tập để hỗ trợ đề xuất nội dung ôn tập phù hợp.

### 4.5. Dashboard và Study Plan

- Dashboard theo dõi tiến độ học tập.
- Hiển thị hiệu suất và kỹ năng.
- Quản lý kế hoạch học tập.
- Hỗ trợ các thao tác quản lý vòng đời Study Plan.

**Giới hạn hiện tại:** Study Plan đã có phần quản lý kế hoạch, nhưng luồng thực hiện bài tập trực tiếp từ từng nhiệm vụ trong kế hoạch vẫn cần tiếp tục phát triển.

## 5. Cấu trúc thư mục

```text
toeic-ai-agent/
├── backend/
│   ├── alembic/
│   └── app/
├── frontend/
├── tests/
├── scripts/
├── data/
├── docs/
├── experiments/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 6. Cài đặt trên Windows

### Yêu cầu

- Python 3.12
- Git
- Visual Studio Code
- PowerShell

Mở PowerShell tại thư mục dự án:

```powershell
cd D:\toeic-ai-agent
```

### Tạo môi trường ảo

```powershell
py -3.12 -m venv .venv
```

### Kích hoạt môi trường ảo

```powershell
.\.venv\Scripts\Activate.ps1
```

### Cài đặt dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Kiểm tra dependencies

```powershell
python -m pip check
```

## 7. Cấu hình môi trường

Tạo file `.env` dựa trên `.env.example`.

Điền các biến môi trường cần thiết theo cấu hình của dự án, bao gồm Gemini API key và các thông tin bảo mật khác.

Không đưa các thông tin sau lên Git:

- API keys và secrets.
- File `.env`.
- Database SQLite và dữ liệu cá nhân.
- Các file chứa thông tin nhạy cảm.

## 8. Chạy ứng dụng

Dự án sử dụng hai thành phần chính:

- Backend: FastAPI.
- Frontend: Streamlit.

Cần mở hai terminal PowerShell riêng biệt để chạy đồng thời.

### 8.1. Khởi chạy Backend FastAPI

Mở PowerShell tại thư mục gốc dự án:

```powershell
cd D:\toeic-ai-agent
```

Kích hoạt môi trường ảo nếu chưa kích hoạt:

```powershell
.\.venv\Scripts\Activate.ps1
```

Khởi chạy Backend:

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765
```

Backend API:

```text
http://127.0.0.1:8765
```

Swagger UI:

```text
http://127.0.0.1:8765/docs
```

Kiểm tra trạng thái Backend:

```text
http://127.0.0.1:8765/health
```

Kết quả mong đợi:

```json
{
  "status": "ok"
}
```

### 8.2. Khởi chạy Streamlit Frontend

Mở terminal PowerShell thứ hai tại thư mục gốc dự án.

Kích hoạt môi trường ảo:

```powershell
.\.venv\Scripts\Activate.ps1
```

Khởi chạy Frontend:

```powershell
python -m streamlit run frontend\app.py --server.port 8502
```

Frontend:

```text
http://127.0.0.1:8502
```

### 8.3. Lưu ý

- Khởi chạy Backend trước Frontend.
- Giữ cả hai terminal hoạt động trong quá trình sử dụng ứng dụng.
- Backend và Frontend cần sử dụng cùng cấu hình API URL.
- Cổng Backend `8765` và Frontend `8502` trong hướng dẫn này được chỉ định bởi các lệnh khởi chạy.

## 9. Kiểm thử

Chạy toàn bộ test suite:

```powershell
python -m pytest
```

Chạy một nhóm test cụ thể:

```powershell
python -m pytest tests\frontend -v
```

Kết quả kiểm thử phải được cập nhật dựa trên lần chạy thực tế; không sử dụng kết quả lịch sử để khẳng định trạng thái test hiện tại.

## 10. Tài liệu dự án

Các tài liệu liên quan:

- `docs/PROJECT_PROGRESS.md`: tiến độ triển khai.
- `docs/DATABASE_SCHEMA.md`: thiết kế cơ sở dữ liệu.

## 11. Định hướng phát triển tiếp theo

- Hoàn thiện luồng thực hành bài tập trực tiếp từ Study Plan.
- Phát triển chức năng ôn tập câu trả lời sai.
- Phát triển ôn từ vựng theo chủ đề và word families.
- Cân nhắc flashcards cho việc ghi nhớ từ vựng.
- Hoàn thiện Reading Practice và Full Test Mode.
- Tiếp tục đánh giá chất lượng câu hỏi và nội dung do AI tạo.

---
