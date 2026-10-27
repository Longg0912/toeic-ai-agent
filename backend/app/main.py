
"""Main FastAPI application for the TOEIC Tutor Agent."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.api.routes.auth import (
    router as auth_router,
)
from backend.app.api.routes.questions import (
    router as questions_router,
)
from backend.app.api.routes.quiz_sessions import (
    router as quiz_sessions_router,
)
# 1. Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="TOEIC Tutor Agent API",
    description=(
        "Backend API for the personalized TOEIC learning "
        "and exam preparation system."
    ),
    version="0.1.0",
)


# 2. Đăng ký Authentication Router
app.include_router(auth_router)
app.include_router(questions_router)
app.include_router(quiz_sessions_router)

# 3. Xử lý lỗi HTTP 422 an toàn
@app.exception_handler(RequestValidationError)
async def safe_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Prevent sensitive input from appearing in validation errors."""

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": "Invalid request data.",
        },
    )


# 4. API kiểm tra trạng thái hệ thống
@app.get(
    "/health",
    tags=["System"],
    summary="Check API health",
)
def health_check() -> dict[str, str]:
    """Check whether the FastAPI application is running."""

    return {"status": "ok"}
