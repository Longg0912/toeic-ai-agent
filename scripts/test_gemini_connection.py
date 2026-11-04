import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# Xác định thư mục gốc của dự án
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Đọc cấu hình từ file .env
load_dotenv(PROJECT_ROOT / ".env")

# Lấy API key và model
api_key = os.getenv("GEMINI_API_KEY", "").strip()
model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()


def main():
    if not api_key:
        print("ERROR: Chưa cấu hình GEMINI_API_KEY trong file .env")
        sys.exit(1)

    if not model:
        print("ERROR: GEMINI_MODEL đang bị bỏ trống.")
        sys.exit(1)

    print(f"Đang kiểm tra kết nối Gemini...")
    print(f"Model: {model}")

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: GEMINI_OK",
        )

        answer = response.text

        if answer:
            print("\nKết nối Gemini API thành công!")
            print(f"Phản hồi từ Gemini: {answer.strip()}")
        else:
            print("\nGemini không trả về nội dung văn bản.")

    except Exception as exc:
        print("\nKết nối Gemini API thất bại.")
        print(f"Loại lỗi: {type(exc).__name__}")
        print(f"Chi tiết: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()