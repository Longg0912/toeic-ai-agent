# PROJECT PROGRESS

## Thông tin dự án

Tên: TOEIC Tutor Agent

Đề tài:
Xây dựng AI Agent gia sư cá nhân hóa
hỗ trợ học và luyện thi TOEIC.

Thư mục:
D:\toeic-ai-agent

Ngôn ngữ:
Python 3.12

## Giai đoạn 01: Project Foundation
### 02A.3 - Alembic Migration

Trạng thái: HOÀN THÀNH

- [x] Cài đặt Alembic.
- [x] Khởi tạo Alembic environment.
- [x] Cấu hình alembic.ini.
- [x] Cấu hình env.py.
- [x] Kết nối Alembic với Base.metadata.
- [x] Tạo initial migration bằng autogenerate.
- [x] Review migration trước khi upgrade.
- [x] Chạy alembic upgrade head.
- [x] Kiểm tra 6 bảng Core và alembic_version.
- [x] Xác nhận Alembic current khớp với head.
- [x] Xác minh SQLite Foreign Keys = 1.
- [x] Chạy 11 database tests thành công.
- [x] Xác nhận hoàn thành 02A.3.

Revision ID: 96035621403c
Database: data/toeic.sqlite3
Kết quả Pytest: 11 passed in 1.65s

Bước tiếp theo: 02A.4 - Quiz Database.

### 02A.4 - Quiz Database

Trạng thái: ĐANG TRIỂN KHAI

#### 02A.4.1 - SQLAlchemy Quiz Models

Trạng thái: CHỜ KIỂM THỬ TỔNG HỢP

- [x] Tạo models/quiz.py.
- [x] Khai báo QuizSession.
- [x] Khai báo QuizItem.
- [x] Khai báo Attempt.
- [x] Đăng ký 3 models mới.
- [x] Kiểm thử 4 Quiz metadata tests.
- [x] Kiểm tra SQLAlchemy nhận đủ 9 bảng.
- [x] Xác nhận database SQLite chưa bị thay đổi.
- [x] Chạy tổng hợp 15 database tests.
- [x] Xác nhận hoàn thành 02A.4.1.

Alembic hiện tại: 96035621403c
SQLite hiện tại: 6 bảng Core + alembic_version

#### 02A.4.2 - Migration
#### 02A.4.2 - Quiz Migration

Trạng thái: HOÀN THÀNH

- [x] Tạo Alembic revision thứ hai.
- [x] Kiểm tra down_revision.
- [x] Review 3 bảng Quiz.
- [x] Kiểm tra PK, FK, UNIQUE, CHECK.
- [x] Kiểm tra indexes.
- [x] Kiểm tra thứ tự upgrade và downgrade.
- [x] Xác nhận không thay đổi Core ngoài dự kiến.
- [x] Cập nhật test_migrations.py.
- [x] Chạy 15 database tests thành công.
- [x] Xác nhận hoàn thành 02A.4.2.

Revision mới: da7ab3c9873a
Revision trước: 96035621403c

Kết quả: 15/15 PASSED.

Bước tiếp theo:
02A.4.3 - Upgrade SQLite và kiểm thử.

Lưu ý:
Chưa xác nhận migration Quiz đã được áp dụng
trên database ứng dụng.

### 02A.4.3 - Application Database Upgrade

Status: COMPLETED

Database: data/toeic.sqlite3

Applied Revision: da7ab3c9873a
Previous Revision: 96035621403c

### Database Tables

Core:
- users
- student_profiles
- skills
- questions
- question_options
- question_skills

Quiz:
- quiz_sessions
- quiz_items
- attempts

Migration:
- alembic_version

Total: 10 tables

### Verification Results

- Alembic current matches head: PASS
- SQLite Foreign Keys: ENABLED
- Integrity Check: OK
- Foreign Key Violations: 0
- Quiz Constraint Tests: 9 PASSED
- All Database Tests: 24 PASSED

### Migration Status

Quiz Migration: APPLIED AND VERIFIED

Next: 02A.4.4 - Idempotent Seed Data

#### 02A.4.4 - Seed TOEIC Part 5

Trạng thái: ĐANG KIỂM THỬ

- [ ] Kiểm tra revision da7ab3c9873a.
- [ ] Sao lưu database trước khi seed.
- [ ] Tạo scripts/__init__.py.
- [ ] Tạo scripts/seed_toeic_part5.py.
- [ ] Khai báo dữ liệu kỹ năng TOEIC.
- [ ] Khai báo 6 câu hỏi Part 5.
- [ ] Tạo logic phát hiện dữ liệu trùng.
- [ ] Tạo logic rollback khi có xung đột.
- [ ] Viết 4 Seed Tests.
- [ ] Chạy 4 Seed Tests thành công.
- [ ] Chạy tổng hợp 28 Database Tests.
- [ ] Chạy seed lần thứ nhất.
- [ ] Chạy seed lần thứ hai.
- [ ] Xác nhận không tạo dữ liệu trùng.
- [ ] Kiểm tra Integrity và Foreign Keys.
- [ ] Cập nhật DATABASE_SCHEMA.md.
- [ ] Xác nhận hoàn thành 02A.4.4.

### Dữ liệu mẫu

Skills: 5
Questions: 6
Options: 24
Question-Skill Links: 7

### Chính sách dữ liệu

- Câu hỏi AI sinh được đánh dấu draft.
- Không dùng để tính mastery chính thức.
- Không seed tài khoản hoặc mật khẩu.
- Không chỉnh sửa dữ liệu người dùng hiện có.

### Bước tiếp theo

02B - Authentication and Authorization.
### 01B - Nhóm B: FastAPI Foundation

Trạng thái: HOÀN THÀNH

- [x] Xác nhận FastAPI, Uvicorn và HTTPX.
- [x] Tạo backend/app/main.py.
- [x] Khởi tạo FastAPI application.
- [x] Tạo endpoint GET /health.
- [x] Chạy Uvicorn trên cổng 8765.
- [x] Kiểm tra GET /health trả về HTTP 200.
- [x] Kiểm tra Swagger UI tại /docs.
- [x] Tạo tests/api/test_health.py.
- [x] Kiểm thử API: 2/2 PASSED.
- [x] Kiểm thử database: 28/28 PASSED.
- [x] Kiểm thử toàn bộ: 30/30 PASSED.
- [x] Xác nhận hoàn thành FastAPI Foundation.

### Kết quả

FastAPI: 0.143.3
Uvicorn: 0.54.0
HTTPX: 0.28.1

Local API:
http://127.0.0.1:8765

Health:
http://127.0.0.1:8765/health

Swagger UI:
http://127.0.0.1:8765/docs

Pytest:
30 passed, 1 warning in 5.46s

### Ghi chú

- Cổng 8000 gặp WinError 10013.
- Đã khởi động thành công trên cổng 8765.
- Có StarletteDeprecationWarning liên quan HTTPX.
- Chưa kết nối database vào API.
- Chưa triển khai Authentication.
- Chưa triển khai Quiz API.

### Bước tiếp theo

01C - Streamlit Frontend Foundation.
Lưu ý:
FastAPI của Giai đoạn 01B chưa được xác nhận
triển khai. Cần hoàn thiện ứng dụng FastAPI
trước khi xây dựng endpoint xác thực.
### 01C - Streamlit Frontend Foundation

Trạng thái: HOÀN THÀNH

- [x] Tạo frontend/__init__.py.
- [x] Tạo frontend/api_client.py.
- [x] Tạo frontend/app.py.
- [x] Hiển thị giao diện TOEIC AI Tutor.
- [x] Chạy Streamlit trên cổng 8502.
- [x] Kết nối FastAPI trên cổng 8765.
- [x] Hiển thị thông báo kết nối thành công.
- [x] Xử lý lỗi khi FastAPI bị tắt.
- [x] Streamlit vẫn hoạt động khi Backend ngừng chạy.
- [x] Chạy 5 Frontend Tests thành công.
- [x] Chạy tổng hợp 35 Tests thành công.
- [x] Xác nhận hoàn thành 01C.

### Kết quả

Frontend: http://127.0.0.1:8502
Backend: http://127.0.0.1:8765

Pytest: 35 passed, 1 warning in 6.03s

### Bước tiếp theo

02B - Authentication & Authorization.
### Nhóm A: Cấu trúc và cấu hình

- [ ] Kiểm tra Python.
- [ ] Kiểm tra quyền ghi thư mục.
- [ ] Tạo môi trường ảo .venv.
- [ ] Kích hoạt môi trường ảo.
- [ ] Chọn Python interpreter trong VS Code.
- [ ] Tạo cấu trúc thư mục dự án.
- [ ] Tạo requirements.txt.
- [ ] Tạo .gitignore.
- [ ] Tạo .env.example.
- [ ] Tạo README.md.
- [ ] Tạo PROJECT_PROGRESS.md.
- [ ] Cài đặt dependencies.
- [ ] Kiểm tra dependencies.
- [ ] Khởi tạo Git.
- [ ] Kiểm tra Git không theo dõi dữ liệu nhạy cảm.
- [ ] Xác nhận Nhóm A thành công.

### 02B.1 - Password Hashing & Verification

Trạng thái: HOÀN THÀNH

- [x] Cài đặt pwdlib và Argon2.
- [x] Triển khai hash_password().
- [x] Triển khai verify_password().
- [x] Viết 8 bài kiểm thử bảo mật mật khẩu.
- [x] Chạy 8/8 Password Security Tests.
- [x] Chạy tổng hợp 43/43 Tests.

Kết quả:
43 passed, 1 warning in 8.05s

Bước tiếp theo:
02B.2.1 - Registration Schemas.
### 02B.2.1 - Registration Schemas

Trạng thái: HOÀN THÀNH

- [x] Cài đặt email-validator.
- [x] Tạo backend/app/schemas/__init__.py.
- [x] Tạo backend/app/schemas/auth.py.
- [x] Xây dựng UserRegisterRequest.
- [x] Xây dựng UserPublic.
- [x] Kiểm tra email và mật khẩu.
- [x] Ngăn người dùng tự khai báo role.
- [x] Không xuất password_hash qua UserPublic.
- [x] Tạo tests/schemas/test_auth_schemas.py.
- [x] Chạy 10 Registration Schema Tests.
- [x] Chạy tổng hợp 53 Tests.
- [x] Xác nhận hoàn thành 02B.2.1.

Kết quả:
53 passed, 1 warning in 6.06s

Database Migration: Không thay đổi.

Bước tiếp theo:
02B.2.2 - Registration Service.
### 02B.2.2 - Registration Service

Trạng thái: HOÀN THÀNH

- [x] Xác minh User Model.
- [x] Tạo backend/app/services/__init__.py.
- [x] Tạo backend/app/services/registration.py.
- [x] Triển khai find_user_by_email().
- [x] Triển khai register_student().
- [x] Băm mật khẩu bằng Argon2id.
- [x] Gán role student từ backend.
- [x] Xử lý email trùng.
- [x] Xử lý IntegrityError và rollback.
- [x] Chỉ trả về UserPublic.
- [x] Tạo tests/services/test_registration.py.
- [x] Chạy 7 Registration Service Tests.
- [x] Chạy tổng hợp 60 Tests.
- [x] Xác nhận hoàn thành 02B.2.2.

### Kết quả

Pytest: 60 passed, 1 warning in 7.86s

Database Migration: Không thay đổi.
Alembic Revision: da7ab3c9873a

### Bước tiếp theo

02B.2.3 - Registration API Endpoint.

Chưa triển khai:
- POST /auth/register
- Login API
- JWT Authentication
- Role-based Authorization
### 02B.2.3 - Registration API Endpoint

Trạng thái: HOÀN THÀNH

- [x] Tạo Authentication Router.
- [x] Tạo dependency get_db().
- [x] Triển khai POST /auth/register.
- [x] Trả về HTTP 201 khi đăng ký thành công.
- [x] Trả về HTTP 409 khi email trùng.
- [x] Xử lý HTTP 422 không làm lộ mật khẩu.
- [x] Đăng ký auth_router trong main.py.
- [x] Giữ nguyên GET /health.
- [x] Tạo tests/api/test_register.py.
- [x] Chạy 9 Registration API Tests thành công.
- [x] Chạy tổng hợp 69 Tests thành công.
- [x] Xác nhận hoàn thành 02B.2.3.

### Kết quả

Pytest: 69 passed, 1 warning in 7.92s

API đã triển khai:
- GET /health
- POST /auth/register

Database Migration: Không thay đổi.
Alembic Revision: da7ab3c9873a

### Bước tiếp theo
### 02B.3.2 - Login Schema & Authentication Service

Trạng thái: HOÀN THÀNH

- [x] Tạo backend/app/schemas/login.py.
- [x] Triển khai UserLoginRequest.
- [x] Triển khai TokenResponse.
- [x] Tạo backend/app/services/authentication.py.
- [x] Triển khai InvalidCredentialsError.
- [x] Triển khai login_user().
- [x] Tái sử dụng find_user_by_email().
- [x] Tái sử dụng verify_password().
- [x] Kiểm tra trạng thái is_active.
- [x] Giảm chênh lệch thời gian với tài khoản không tồn tại.
- [x] Không cấp JWT khi xác thực thất bại.
- [x] Viết 9 Login Schema Tests.
- [x] Viết 8 Authentication Service Tests.
- [x] Chạy tổng hợp 100 Tests thành công.
- [x] Xác nhận hoàn thành 02B.3.2.

### Kết quả kiểm thử

Login Schema Tests: 9 PASSED
Authentication Service Tests: 8 PASSED

Tổng cộng:
100 passed, 1 warning in 21.68s

### Authentication

Password Hashing: Argon2id
JWT Algorithm: HS256
Access Token Lifetime: 30 minutes

### Database

Không thay đổi SQLAlchemy Models.
Không tạo Alembic Migration mới.

Revision: da7ab3c9873a

### Chưa triển khai

- POST /auth/login
- JWT Bearer Authentication Dependency
- Current User Authentication
- Role-based Authorization
- Rate Limiting

### Bước tiếp theo

02B.3.3 - Login API Endpoint.
### 02B.3.3 - Login API & JWT Endpoint

Trạng thái: HOÀN THÀNH

- [x] Triển khai POST /auth/login.
- [x] Tái sử dụng Authentication Service.
- [x] Trả về HTTP 200 và JWT Access Token.
- [x] Trả về HTTP 401 khi xác thực thất bại.
- [x] Xử lý HTTP 422 an toàn.
- [x] Không làm lộ mật khẩu trong response.
- [x] Bổ sung Cache-Control: no-store.
- [x] Tạo tests/api/test_login.py.
- [x] Chạy 14 Login API Tests thành công.
- [x] Chạy tổng hợp 114 Tests thành công.
- [x] Xác nhận hoàn thành 02B.3.3.

### Kết quả

Pytest: 114 passed, 1 warning in 16.21s

API Authentication:
- POST /auth/register
- POST /auth/login

JWT Algorithm: HS256
Access Token Lifetime: 30 minutes

Database Migration: Không thay đổi.
Alembic Revision: da7ab3c9873a

### Bước tiếp theo

02B.4 - Current User Authentication.
### 02B.4.1 - JWT Bearer Dependency & Current User

Trạng thái: HOÀN THÀNH

- [x] Tạo backend/app/api/auth_deps.py.
- [x] Khai báo HTTPBearer Security Scheme.
- [x] Triển khai credentials_exception().
- [x] Triển khai get_current_user().
- [x] Đọc Authorization: Bearer JWT.
- [x] Tái sử dụng decode_access_token().
- [x] Tra cứu User trong SQLite bằng SQLAlchemy.
- [x] Kiểm tra trạng thái is_active.
- [x] Trả HTTP 401 khi thiếu JWT.
- [x] Trả HTTP 401 khi JWT sai hoặc hết hạn.
- [x] Trả HTTP 401 khi User không tồn tại.
- [x] Trả HTTP 401 khi User bị vô hiệu hóa.
- [x] Tạo tests/api/test_auth_deps.py.
- [x] Sử dụng SQLite tạm và JWT Secret Key riêng.
- [x] Chạy 13 Authentication Dependency Tests.
- [x] Chạy tổng hợp 127 Tests.
- [x] Xác nhận hoàn thành 02B.4.1.

### Kết quả

Pytest: 127 passed, 1 warning in 21.65s

Authentication Dependency:
get_current_user()

Security:
HTTPBearer + HS256 JWT

Successful Result:
Authenticated User ORM object

Authentication Failure:
HTTP 401 Unauthorized

Database Migration:
Không thay đổi.

Alembic Revision: da7ab3c9873a

### Bước tiếp theo
### 02B.4.2 - GET /auth/me & API Tests

Trạng thái: HOÀN THÀNH

- [x] Triển khai GET /auth/me.
- [x] Tái sử dụng get_current_user().
- [x] Trả về UserPublic.
- [x] Kiểm tra Bearer JWT.
- [x] Xử lý HTTP 401 khi thiếu hoặc sai JWT.
- [x] Từ chối JWT hết hạn.
- [x] Từ chối tài khoản không tồn tại.
- [x] Từ chối tài khoản inactive.
- [x] Không trả mật khẩu hoặc password_hash.
- [x] Kiểm tra đúng chủ sở hữu JWT.
- [x] Tạo tests/api/test_me.py.
- [x] Kiểm thử sử dụng SQLite tạm.
- [x] Chạy 14 GET /auth/me Tests.
- [x] Chạy tổng hợp 141 Tests.
- [x] Xác nhận hoàn thành 02B.4.2.

Kết quả:
141 passed, 1 warning in 25.89s

API hiện có:
- GET /health
- POST /auth/register
- POST /auth/login
- GET /auth/me

Database Migration: Không thay đổi.
Alembic Revision: da7ab3c9873a

Kiểm tra thủ công Swagger UI:
Chưa xác nhận.

Bước tiếp theo:
### 02B.5.1 - Role-Based Access Control

Trạng thái: HOÀN THÀNH

- [x] Tạo backend/app/api/authorization.py.
- [x] Khai báo UserRole: student, admin.
- [x] Triển khai require_role().
- [x] Tái sử dụng get_current_user().
- [x] Kiểm tra role trực tiếp từ User ORM.
- [x] Trả HTTP 403 khi không đủ quyền.
- [x] Giữ HTTP 401 khi chưa xác thực hợp lệ.
- [x] Hỗ trợ nhiều role được phép.
- [x] Từ chối cấu hình role không hợp lệ.
- [x] Không tin role claim trong JWT.
- [x] Tạo tests/api/test_authorization.py.
- [x] Kiểm thử với SQLite tạm.
- [x] Kiểm thử Student và Admin.
- [x] Kiểm thử thăng quyền và hạ quyền.
- [x] Chạy 16 RBAC Tests.
- [x] Chạy tổng hợp 157 Tests.
- [x] Xác nhận hoàn thành 02B.5.1.

### Kết quả

Pytest: 157 passed, 1 warning in 28.73s

Authentication:
get_current_user()

Authorization:
require_role(*allowed_roles)

Supported Roles:
- student
- admin

Permission Source:
User.role from SQLite

Authentication Failure:
HTTP 401 Unauthorized

Authorization Failure:
HTTP 403 Forbidden

Database Migration: Không thay đổi.
Alembic Revision: da7ab3c9873a

### Bước tiếp theo

### 02B.5.2 - Resource Ownership & Access Control

Trạng thái: HOÀN THÀNH

- [x] Tạo backend/app/api/ownership.py.
- [x] Triển khai get_owned_quiz_session().
- [x] Tái sử dụng require_role("student").
- [x] Tái sử dụng get_current_user().
- [x] Kiểm tra QuizSession.id.
- [x] Kiểm tra QuizSession.user_id = current_user.id.
- [x] Thực hiện ownership filtering trong SQL.
- [x] Trả HTTP 401 nếu chưa xác thực.
- [x] Trả HTTP 403 nếu không có role student.
- [x] Trả HTTP 404 nếu tài nguyên không tồn tại.
- [x] Trả HTTP 404 nếu tài nguyên thuộc người khác.
- [x] Kiểm thử ngăn truy cập và sửa bài của người khác.
- [x] Kiểm thử bằng SQLite tạm.
- [x] Chạy 14 Resource Ownership Tests.
- [x] Chạy tổng hợp 171 Tests.
- [x] Xác nhận hoàn thành 02B.5.2.

### Kết quả

Pytest: 171 passed, 1 warning in 40.94s

Ownership Dependency:
get_owned_quiz_session()

Resource:
QuizSession

Owner:
QuizSession.user_id

Authenticated User:
current_user.id

Authentication Failure: HTTP 401
Authorization Failure: HTTP 403
Missing or Non-owned Resource: HTTP 404

Database Migration: Không thay đổi.
Alembic Revision: da7ab3c9873a

### Bước tiếp theo

### 02B.5.3 - Authorization Security Tests

Trạng thái: HOÀN THÀNH

- [x] Tạo tests/security/test_authorization_security.py.
- [x] Kiểm thử IDOR/BOLA giữa các học viên.
- [x] Kiểm tra request trái phép không sửa dữ liệu.
- [x] Kiểm thử giả mạo user_id và owner_id.
- [x] Kiểm thử JWT có role claim giả.
- [x] Kiểm thử JWT có owner claim giả.
- [x] Kiểm thử JWT bị giả mạo chữ ký.
- [x] Kiểm thử JWT claims bắt buộc.
- [x] Từ chối thuật toán JWT không được phép.
- [x] Kiểm thử tài khoản bị vô hiệu hóa.
- [x] Kiểm thử thay đổi role.
- [x] Kiểm thử Quiz Session ID không hợp lệ.
- [x] Kiểm thử bằng SQLite tạm.
- [x] Chạy 24 Authorization Security Tests.
- [x] Chạy tổng hợp 195 Tests.
- [x] Xác nhận hoàn thành 02B.5.3.

### Kết quả

Pytest: 195 passed, 1 warning in 47.54s

### Authentication & Authorization

- JWT Authentication: HOÀN THÀNH
- Current User Authentication: HOÀN THÀNH
- Role-Based Access Control: HOÀN THÀNH
- QuizSession Resource Ownership: HOÀN THÀNH
- Authorization Security Tests: HOÀN THÀNH

### Database

Không thay đổi SQLAlchemy Models.
Không tạo Alembic Migration.

Alembic Revision: da7ab3c9873a

### Known Limitations

- Chưa tích hợp Ownership vào API Quiz thực tế.
- Chưa triển khai Rate Limiting.
- Chưa có Audit Logging.
- Chưa có Token Revocation.
- Chưa thực hiện kiểm thử bảo mật production.

### Bước tiếp theo

### 02B.6.1 - Streamlit Authentication API Client

Trạng thái: HOÀN THÀNH

- [x] Tạo frontend/auth_api_client.py.
- [x] Triển khai AuthAPIClient.
- [x] Triển khai PublicUser.
- [x] Triển khai LoginResult.
- [x] Triển khai AuthAPIError.
- [x] Triển khai register().
- [x] Triển khai login().
- [x] Triển khai get_me().
- [x] Gửi Bearer JWT qua Authorization Header.
- [x] Xử lý các mã lỗi HTTP.
- [x] Xử lý Timeout và Connection Error.
- [x] Không làm lộ mật khẩu hoặc JWT trong thông báo lỗi.
- [x] Ngăn HTTP Redirect ngoài dự kiến.
- [x] Yêu cầu HTTPS với Backend ngoài localhost.
- [x] Tạo tests/frontend/test_auth_api_client.py.
- [x] Kiểm thử bằng httpx.MockTransport.
- [x] Chạy 18 Authentication API Client Tests.
- [x] Chạy tổng hợp 213 Tests.
- [x] Xác nhận hoàn thành 02B.6.1.

### Kết quả

Pytest: 213 passed, 1 warning in 36.48s

API Client:
frontend/auth_api_client.py

Class:
AuthAPIClient

Methods:
- register(email, password)
- login(email, password)
- get_me(access_token)

Backend URL:
http://127.0.0.1:8765

### Known Limitations

- Chưa xây dựng giao diện đăng ký/đăng nhập.
- Chưa triển khai Streamlit Session State.
- Chưa có chức năng đăng xuất.
- Chưa kiểm thử tích hợp Frontend–Backend thực tế.

### Database

Không thay đổi SQLAlchemy Models.
Không tạo Alembic Migration mới.

Alembic Revision: da7ab3c9873a

### Bước tiếp theo

### 02B.6.2 - Streamlit Login/Register UI & Session State

Trạng thái: HOÀN THÀNH

- [x] Hoàn thành giao diện đăng ký.
- [x] Hoàn thành giao diện đăng nhập.
- [x] Hoàn thành quản lý phiên JWT.
- [x] Hoàn thành trang hồ sơ học viên.
- [x] Hoàn thành chức năng đăng xuất.
- [x] Kiểm thử 14 Authentication UI Tests.
- [x] Kiểm thử toàn dự án: 227 passed.
- [x] Kiểm tra giao diện thực tế.

Kết quả: 227 passed, 1 warning in 38.65s

Bước tiếp theo:
02B.6.3 - Frontend–Backend Integration Tests
### Nhóm B: FastAPI

- [ ] Tạo FastAPI application.
- [ ] Tạo endpoint GET /health.
- [ ] Kiểm tra /health.
- [ ] Kiểm tra /docs.

### Nhóm C: Streamlit

- [ ] Tạo giao diện đầu tiên.
- [ ] Kết nối đến FastAPI.
- [ ] Hiển thị trạng thái Backend.
- [ ] Xử lý lỗi kết nối.

### Nhóm D: Pytest

- [ ] Viết test GET /health.
- [ ] Chạy pytest.
- [ ] Xác nhận kết quả kiểm thử.

## Kết quả kiểm tra

Chưa được xác nhận trên máy của người thực hiện.

## Vấn đề cần theo dõi

- Đã từng gặp WinError 5 khi tạo .venv trên ổ D.
- Cần xác nhận lỗi quyền truy cập đã được xử lý.

## Các chức năng chưa triển khai

- Database
- Authentication
- TOEIC Question Bank
- Scoring Engine
- Student Modeling
- Adaptive Recommendation
- RAG
- Tutor Agent
- Giao diện học tập hoàn chỉnh

## Bước tiếp theo

Hoàn thành và xác nhận Nhóm A.

Sau khi được xác nhận, chuyển sang Nhóm B.