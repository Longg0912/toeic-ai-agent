# PROJECT PROGRESS

## 1. Thông tin dự án

- **Tên dự án:** TOEIC Tutor Agent
- **Đề tài:** Xây dựng AI Agent gia sư cá nhân hóa hỗ trợ học và luyện thi TOEIC.
- **Thư mục:** `D:\toeic-ai-agent`
- **Ngôn ngữ:** Python 3.12
- **Frontend:** Streamlit
- **Backend:** FastAPI
- **AI Model:** Google Gemini API

## 2. Trạng thái tổng quan

Dự án đã hoàn thành nền tảng Backend, Database, Authentication, RAG, Gemini Tutor Agent, Student Modeling, Adaptive Recommendation, Dashboard và Study Plan ở các mức độ khác nhau.

Các chức năng giao diện Dashboard, Study Plan và Text Selection AI Tutor đã được triển khai và commit.

| Hạng mục | Trạng thái |
|---|---|
| Project Foundation | HOÀN THÀNH |
| Database và Alembic | HOÀN THÀNH CÁC MILESTONE ĐÃ TRIỂN KHAI |
| Authentication và Authorization | HOÀN THÀNH |
| Streamlit Authentication UI | HOÀN THÀNH |
| TOEIC Question Bank và Quiz Backend | ĐÃ TRIỂN KHAI |
| RAG và Document Processing | ĐÃ TRIỂN KHAI |
| Gemini Tutor Agent | ĐÃ TRIỂN KHAI |
| Student Modeling | ĐÃ TRIỂN KHAI |
| Adaptive Recommendation | ĐÃ TRIỂN KHAI |
| Study Plan Backend | ĐÃ TRIỂN KHAI |
| Dashboard Backend và Frontend | ĐÃ TRIỂN KHAI |
| Study Plan Frontend | ĐÃ TRIỂN KHAI |
| Text Selection AI Tutor | MVP HOÀN THÀNH |
| Reading Practice Part 5–7 | TIẾP TỤC PHÁT TRIỂN |
| Full Test Mode 100 câu / 75 phút | CHƯA XÁC NHẬN HOÀN THÀNH |
| Thực hành bài tập trực tiếp từ Study Plan | CHƯA HOÀN THÀNH |

Lưu ý: Trạng thái "đã triển khai" không đồng nghĩa mọi chức năng liên quan đã hoàn thiện hoặc đã được kiểm thử trên môi trường production.

## 3. Kiến trúc và công nghệ

### 3.1. Backend

- FastAPI
- Uvicorn
- SQLAlchemy 2.x
- Alembic
- SQLite
- Pydantic
- JWT Authentication
- Role-Based Access Control

### 3.2. Frontend

- Streamlit
- API Clients
- Session State
- Dashboard UI
- Study Plan UI
- Text Selection Component

### 3.3. AI và RAG

- Google Gemini API (`google-genai`)
- Gemini Function Calling
- ChromaDB
- Sentence Transformers
- Document Processing
- Retrieval-Augmented Generation

### 3.4. Testing

- Pytest
- FastAPI TestClient
- HTTPX
- SQLite test database
- Frontend component tests

## 4. Các hạng mục đã triển khai

### 4.1. Project Foundation

- [x] Khởi tạo cấu trúc dự án.
- [x] Thiết lập môi trường Python.
- [x] Thiết lập requirements.txt.
- [x] Thiết lập .gitignore.
- [x] Tạo .env.example.
- [x] Khởi tạo Git repository.
- [x] Tạo FastAPI application.
- [x] Tạo endpoint `GET /health`.
- [x] Tích hợp Streamlit với Backend.
- [x] Thiết lập Pytest.

### 4.2. Database và Alembic

- [x] SQLAlchemy Models.
- [x] User và Student Profile.
- [x] TOEIC Question Models.
- [x] Quiz Session, Quiz Item và Attempt.
- [x] Alembic Migration.
- [x] SQLite Foreign Key Enforcement.
- [x] Seed dữ liệu TOEIC Part 5.
- [x] RAG database tables.
- [x] Document ownership.
- [x] Study Plan database tables.

Các migration quan trọng đã được triển khai:

- `a91e6c4d2f80`: Global RAG tables.
- `e2f7a6c91d34`: Page number.
- `f1a9c3d7e205`: Personal document ownership.
- `f2f8eab7a67a`: Study Plan tables.

Lưu ý: Cần đối chiếu Alembic revision hiện tại trên máy với lịch sử migration trước khi thực hiện migration mới.

### 4.3. Authentication và Authorization

- [x] Password hashing bằng Argon2id.
- [x] Password verification.
- [x] Registration Schema.
- [x] Registration Service.
- [x] `POST /auth/register`.
- [x] Login Schema.
- [x] Authentication Service.
- [x] `POST /auth/login`.
- [x] JWT HS256.
- [x] JWT Bearer Dependency.
- [x] `GET /auth/me`.
- [x] Current User Authentication.
- [x] Role-Based Access Control.
- [x] Student và Admin roles.
- [x] Resource Ownership.
- [x] Authorization Security Tests.
- [x] Streamlit Authentication API Client.
- [x] Login/Register UI.
- [x] Session State.
- [x] Logout.
- [x] Student Profile UI.

### 4.4. TOEIC Question Bank và Quiz Backend

- [x] Question Models.
- [x] Question Options.
- [x] Question-Skill Relationships.
- [x] Quiz Session.
- [x] Quiz Items.
- [x] Attempts.
- [x] Quiz Database Migration.
- [x] Quiz Session API.
- [x] Submit và grading theo answer key.
- [x] Quiz History và Review.
- [x] Ownership validation.
- [x] Quiz API tests.

Phạm vi luyện Reading mục tiêu:

- Reading Practice Mode: luyện từng Part.
- Full Test Mode: Part 5–7, 100 câu, 75 phút.

Full Test Mode và luồng luyện tập hoàn chỉnh vẫn cần tiếp tục được triển khai và xác nhận.

### 4.5. RAG và Document Processing

- [x] Document Processing.
- [x] Embedding Service.
- [x] ChromaDB Integration.
- [x] Indexing Service.
- [x] Retrieval Service.
- [x] Global RAG Tables.
- [x] Personal Document Ownership.
- [x] Page Number Metadata.
- [x] RAG Tools cho Tutor Agent.

### 4.6. Gemini Tutor Agent

- [x] Tích hợp Google Gemini API.
- [x] Gemini Tutor Service.
- [x] Function Calling.
- [x] Tool Registry.
- [x] Recommendation Tool.
- [x] Global RAG Tool.
- [x] Trusted Student Context.
- [x] Tutor Chat API.
- [x] Tutor API Client.
- [x] Tutor Chat Tests.

Gemini được sử dụng để giải thích và hỗ trợ học tập. Việc chấm điểm câu hỏi TOEIC chính thức vẫn dựa trên answer key do hệ thống quản lý.

### 4.7. Student Modeling và Adaptive Recommendation

- [x] Student Modeling Services.
- [x] Theo dõi kết quả học tập.
- [x] Phân tích kỹ năng.
- [x] Adaptive Recommendation.
- [x] Kết nối thông tin học tập với Tutor Agent.

### 4.8. Study Plan

Backend:

- [x] Study Plan Database Models.
- [x] Study Plan Service.
- [x] Adaptive Planner.
- [x] Study Plan Lifecycle API.
- [x] Tạo Study Plan.
- [x] Xem Study Plan.
- [x] Pause Study Plan.
- [x] Resume Study Plan.
- [x] Complete Study Plan.

Frontend:

- [x] Study Plan API Client.
- [x] Study Plan UI.
- [x] Study Plan Tests.

Các chức năng cần tiếp tục:

- [ ] Thực hiện bài tập trực tiếp từ từng nhiệm vụ trong Study Plan.
- [ ] Theo dõi hoàn thành từng nhiệm vụ.
- [ ] Ôn tập câu trả lời sai.
- [ ] Ôn từ vựng theo chủ đề.
- [ ] Hỗ trợ word families.
- [ ] Cân nhắc flashcards.
- [ ] Tạo quiz ôn tập kiến thức đã học.

### 4.9. Dashboard

Backend:

- [x] Dashboard Overview API.
- [x] Performance API.
- [x] Skills API.
- [x] Activity API.
- [x] Study Plan Dashboard API.

Frontend:

- [x] Dashboard API Client.
- [x] Dashboard UI.
- [x] Hiển thị tiến độ học tập.
- [x] Hiển thị hiệu suất.
- [x] Hiển thị kỹ năng cần cải thiện.
- [x] Dashboard UI Tests.

### 4.10. Text Selection AI Tutor

- [x] Tutor Selection Context Schema.
- [x] Selection Context Service.
- [x] Kiểm tra quyền sở hữu Quiz Session.
- [x] Kiểm tra nội dung được chọn.
- [x] Kiểm tra ngữ cảnh câu hỏi và bài đọc.
- [x] Kiểm soát việc tiết lộ đáp án khi bài chưa nộp.
- [x] Tích hợp Selection Context vào Tutor Chat API.
- [x] Gemini nhận ngữ cảnh bài tập.
- [x] Text Selection Component.
- [x] Floating Ask AI Toolbar.
- [x] Tích hợp vào Quiz UI.
- [x] Tutor multi-turn chat theo ngữ cảnh được chọn.
- [x] Backend và Frontend Tests.
- [x] Kiểm tra thao tác chọn văn bản và hỏi AI trên trình duyệt.

**Trạng thái:** MVP hoàn thành. Có thể chọn văn bản trong bài luyện tập, gửi cho AI và nhận giải thích theo ngữ cảnh.

## 5. Kết quả kiểm thử

Các kết quả dưới đây là kết quả đã được ghi nhận trong quá trình triển khai, không phải kết quả chạy lại sau các commit tài liệu.

### 5.1. Các mốc kiểm thử

- Database và Alembic: các nhóm test đã hoàn thành theo từng milestone.
- Authentication và Authorization: các nhóm test đã hoàn thành theo từng milestone.
- Study Plan Service và API: đã kiểm thử qua các milestone.
- Dashboard API và Client: đã kiểm thử.
- Dashboard UI: 4 tests passed.
- Study Plan UI: 7 tests passed.
- Text Selection: các nhóm test Schema, Service, API Client và Component đã được kiểm thử.

### 5.2. Kết quả toàn bộ test suite gần nhất được báo cáo

**811 passed, 3 warnings, 0 failed.**

Thời gian chạy được báo cáo: 143.27 giây.

Ba warnings là Starlette deprecation warnings liên quan đến `HTTP_422_UNPROCESSABLE_ENTITY` trong một số test API.

Cần chạy lại toàn bộ test suite để xác nhận trạng thái mới nhất trước khi phát hành hoặc đưa ra kết luận về chất lượng hiện tại.

## 6. Kiểm tra khởi chạy ứng dụng

### 6.1. Backend

Lệnh chạy:

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765
```

Địa chỉ:

- API: `http://127.0.0.1:8765`
- Health: `http://127.0.0.1:8765/health`
- Swagger UI: `http://127.0.0.1:8765/docs`

Đã xác nhận trên trình duyệt:

- Health trả về `{"status":"ok"}`.
- Swagger UI hiển thị API.

### 6.2. Frontend

Lệnh chạy:

```powershell
python -m streamlit run frontend\app.py --server.port 8502
```

Địa chỉ:

`http://localhost:8502`

Đã xác nhận giao diện Dashboard hiển thị trên trình duyệt.

Cần tiếp tục kiểm tra các trang Study Planner, AI Tutor và TOEIC Quiz trong lần xác minh giao diện tiếp theo.

## 7. Các vấn đề và giới hạn còn lại

### 7.1. Study Plan

- Chưa có luồng thực hiện bài tập trực tiếp từ từng nhiệm vụ.
- Chưa hoàn thiện hệ thống ôn tập câu sai.
- Chưa hoàn thiện ôn từ vựng theo chủ đề và word families.

### 7.2. TOEIC Practice

- Tiếp tục hoàn thiện Reading Practice Mode.
- Hoàn thiện quy trình Full Test Mode.
- Kiểm tra số lượng câu, thời gian làm bài và quy trình chấm điểm.
- Tiếp tục kiểm duyệt nội dung do AI tạo trước khi đưa vào Question Bank.

### 7.3. AI Tutor

- Tiếp tục đánh giá chất lượng câu trả lời của Gemini.
- Đánh giá độ chính xác của RAG.
- Kiểm tra khả năng giải thích câu hỏi theo ngữ cảnh.
- Tiếp tục cải thiện trải nghiệm Tutor trong quá trình làm bài.

### 7.4. Technical Debt

- Xử lý các Starlette deprecation warnings.
- Tiếp tục kiểm tra quyền sở hữu tài nguyên ở các API.
- Đánh giá logging và error handling.
- Rà soát cấu hình môi trường trước khi triển khai production.

## 8. Roadmap tiếp theo

### Ưu tiên 1 – Hoàn thiện Study Plan Practice

- [ ] Thiết kế luồng thực hiện bài tập từ Study Plan.
- [ ] Liên kết nhiệm vụ học tập với Question Bank.
- [ ] Lưu kết quả hoàn thành từng nhiệm vụ.
- [ ] Tạo luồng ôn tập câu trả lời sai.
- [ ] Xây dựng ôn từ vựng theo chủ đề.
- [ ] Xem xét flashcards.

### Ưu tiên 2 – Hoàn thiện TOEIC Reading Practice

- [ ] Hoàn thiện luyện tập từng Part.
- [ ] Bổ sung và kiểm thử Part 6–7.
- [ ] Hoàn thiện Full Test Mode.
- [ ] Kiểm thử giới hạn 100 câu và 75 phút.
- [ ] Hoàn thiện báo cáo kết quả bài thi.

### Ưu tiên 3 – Cải thiện AI Tutor

- [ ] Đánh giá chất lượng câu trả lời.
- [ ] Đánh giá chất lượng truy xuất RAG.
- [ ] Cải thiện giải thích đáp án và các lựa chọn sai.
- [ ] Tối ưu trải nghiệm hỏi AI trong bài luyện tập.

### Ưu tiên 4 – Hoàn thiện tài liệu và chất lượng

- [ ] Cập nhật DATABASE_SCHEMA.md.
- [ ] Rà soát README.md.
- [ ] Duy trì test suite.
- [ ] Xử lý deprecation warnings.
- [ ] Rà soát bảo mật trước khi triển khai.

## 9. Lịch sử commit quan trọng

Các commit gần nhất đã xác nhận:

| Commit | Nội dung |
|---|---|
| `75c301c` | Dashboard API và services |
| `6d05bb8` | Text Selection AI Tutor |
| `6e1cc35` | Dashboard và Study Plan UI |

Các commit tài liệu sau đó:

| Commit | Nội dung |
|---|---|
| `4ad6488` | Cập nhật README |

Lưu ý: Commit `4ad6488` được tạo sau lần push code gần nhất và cần được push lên GitHub.

## 10. Nguyên tắc phát triển tiếp theo

- Tiếp tục phát triển trên kiến trúc hiện tại.
- Không xây dựng lại các module đã hoàn thành nếu không có lý do kỹ thuật.
- Mỗi bước chỉ triển khai một nhóm chức năng rõ ràng.
- Kiểm tra file hiện tại trước khi chỉnh sửa code.
- Chạy test liên quan sau mỗi thay đổi.
- Chạy toàn bộ test suite trước các milestone lớn.
- Không đưa API keys, `.env`, database cá nhân hoặc dữ liệu nhạy cảm lên Git.
- Không đưa nội dung AI tạo vào Question Bank chính thức khi chưa được kiểm duyệt.

---

**Cập nhật tiến độ:** 25/11/2026

**Trạng thái:** Dự án đã có nền tảng Backend, Frontend, AI Tutor, RAG, Dashboard và Study Plan. Giai đoạn tiếp theo tập trung vào hoàn thiện luồng thực hành và ôn tập trực tiếp từ Study Plan, đồng thời hoàn thiện TOEIC Reading Practice.