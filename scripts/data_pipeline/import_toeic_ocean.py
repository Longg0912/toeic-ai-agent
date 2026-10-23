
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.app.db.models.core import Question, QuestionOption
from backend.app.db.session import SessionLocal, engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_REVISION = "55db8077d91e"

DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "toeic-ocean-part5.jsonl"
)

DEFAULT_REPORT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "toeic-ocean-import-report.json"
)

OPTION_KEYS = ("A", "B", "C", "D")


def nonempty_string(value: Any, field: str, line_number: int) -> str:
    """Validate a required non-empty string."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Dòng {line_number}: trường '{field}' phải là chuỗi "
            "không rỗng."
        )

    return value.strip()


def normalize_text(value: str) -> str:
    """Normalize whitespace and case for duplicate detection."""

    return re.sub(r"\s+", " ", value).strip().casefold()


def content_fingerprint(
    part: int,
    content: str,
    options: dict[str, str],
) -> str:
    """
    Create a stable hash from the question stem and its options.

    The answer key is intentionally excluded. If identical question
    content has conflicting answer keys, the importer raises an error.
    """

    payload = {
        "part": part,
        "content": normalize_text(content),
        "options": {
            key: normalize_text(options[key])
            for key in sorted(options)
        },
    }

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare_record(
    record: dict[str, Any],
    line_number: int = 1,
) -> dict[str, Any]:
    """Validate and normalize one staged question."""

    question_id = nonempty_string(
        record.get("question_id"),
        "question_id",
        line_number,
    )

    source_record_id = nonempty_string(
        record.get("source_record_id"),
        "source_record_id",
        line_number,
    )

    source_name = nonempty_string(
        record.get("source_name"),
        "source_name",
        line_number,
    )

    source_url = nonempty_string(
        record.get("source_url"),
        "source_url",
        line_number,
    )

    content = nonempty_string(
        record.get("text"),
        "text",
        line_number,
    )

    if len(source_name) > 255:
        raise ValueError(
            f"Dòng {line_number}: source_name dài quá 255 ký tự."
        )

    part = record.get("part")

    if type(part) is not int or part != 5:
        raise ValueError(
            f"Dòng {line_number}: importer hiện chỉ nhận Part 5."
        )

    # Never import a record that has a different review or rights status.
    if record.get("reviewed_status") != "pending_review":
        raise ValueError(
            f"Dòng {line_number}: reviewed_status phải là "
            "'pending_review'."
        )

    if record.get("rights_status") != "unknown":
        raise ValueError(
            f"Dòng {line_number}: rights_status phải là 'unknown'."
        )

    raw_options = record.get("options")

    if not isinstance(raw_options, dict):
        raise ValueError(
            f"Dòng {line_number}: options phải là một object."
        )

    if set(raw_options) != set(OPTION_KEYS):
        raise ValueError(
            f"Dòng {line_number}: options phải có đủ A, B, C, D."
        )

    options = {
        key: nonempty_string(
            raw_options[key],
            f"options.{key}",
            line_number,
        )
        for key in OPTION_KEYS
    }

    correct_option = record.get("correct_option")

    if not isinstance(correct_option, str):
        raise ValueError(
            f"Dòng {line_number}: correct_option không hợp lệ."
        )

    correct_option = correct_option.strip().upper()

    if correct_option not in OPTION_KEYS:
        raise ValueError(
            f"Dòng {line_number}: đáp án đúng phải là A, B, C hoặc D."
        )

    raw_difficulty = record.get("difficulty")

    if raw_difficulty is None:
        difficulty = None
    elif (
        type(raw_difficulty) is int
        and 1 <= raw_difficulty <= 5
    ):
        difficulty = raw_difficulty
    else:
        raise ValueError(
            f"Dòng {line_number}: difficulty phải là null "
            "hoặc số nguyên từ 1 đến 5."
        )

    explanation = record.get("explanation")

    if explanation is not None and not isinstance(explanation, str):
        raise ValueError(
            f"Dòng {line_number}: explanation phải là chuỗi hoặc null."
        )

    if isinstance(explanation, str):
        explanation = explanation.strip() or None

    # Use the question-level license, not the repository's license.
    # A repository license does not automatically establish rights
    # to individual question content.
    content_license = record.get("content_license")

    if content_license is not None:
        if not isinstance(content_license, str):
            raise ValueError(
                f"Dòng {line_number}: content_license không hợp lệ."
            )

        content_license = content_license.strip() or None

    if content_license is not None and len(content_license) > 200:
        raise ValueError(
            f"Dòng {line_number}: content_license dài quá 200 ký tự."
        )

    source_reference = (
        f"{source_url.rstrip('/')}#record={source_record_id}"
    )

    fingerprint = content_fingerprint(
        part,
        content,
        options,
    )

    return {
        "question_id": question_id,
        "source_record_id": source_record_id,
        "part": part,
        "content": content,
        "options": options,
        "correct_option_key": correct_option,
        "difficulty": difficulty,
        "explanation": explanation,
        "source_name": source_name,
        "source_reference": source_reference,
        "source_license": content_license,
        "content_hash": fingerprint,
        "fingerprint": fingerprint,
    }


def load_staged_records(input_path: Path) -> list[dict[str, Any]]:
    """Read JSONL and reject malformed or duplicate staged records."""

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy file JSONL: {input_path}"
        )

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_fingerprints: set[str] = set()

    with input_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                raw_record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL lỗi tại dòng {line_number}: {exc}"
                ) from exc

            if not isinstance(raw_record, dict):
                raise ValueError(
                    f"Dòng {line_number} phải chứa một JSON object."
                )

            record = prepare_record(raw_record, line_number)

            if record["question_id"] in seen_ids:
                raise ValueError(
                    f"question_id bị trùng: {record['question_id']}"
                )

            if record["fingerprint"] in seen_fingerprints:
                raise ValueError(
                    "Phát hiện nội dung trùng trong JSONL tại "
                    f"question_id={record['question_id']}. "
                    "Hãy kiểm tra dữ liệu trước khi nhập."
                )

            seen_ids.add(record["question_id"])
            seen_fingerprints.add(record["fingerprint"])
            records.append(record)

    if not records:
        raise ValueError("File JSONL không có bản ghi hợp lệ.")

    return records


def validate_database(session, requested_owner_id: int | None) -> int:
    """Verify schema, migration state, FK integrity and owner."""

    if engine.dialect.name != "sqlite":
        raise RuntimeError("Importer hiện chỉ hỗ trợ SQLite.")

    revision = session.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()

    if revision != EXPECTED_REVISION:
        raise RuntimeError(
            f"Revision hiện tại là {revision!r}; "
            f"cần {EXPECTED_REVISION!r}."
        )

    connection = session.connection()

    fk_enabled = connection.exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar_one()

    violations = connection.exec_driver_sql(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if fk_enabled != 1 or violations:
        raise RuntimeError(
            "Database không vượt qua kiểm tra khóa ngoại: "
            f"enabled={fk_enabled}, violations={violations!r}"
        )

    columns = {
        row[1]
        for row in connection.exec_driver_sql(
            "PRAGMA table_info(questions)"
        ).fetchall()
    }

    required_columns = {
        "owner_user_id",
        "part",
        "content",
        "correct_option_key",
        "difficulty",
        "explanation",
        "review_status",
        "source_type",
        "source_name",
        "source_reference",
        "source_license",
        "usage_permission_status",
        "visibility",
        "content_hash",
    }

    missing_columns = required_columns - columns

    if missing_columns:
        raise RuntimeError(
            f"Thiếu cột trong bảng questions: {sorted(missing_columns)}"
        )

    schema_sql = session.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='questions'"
        )
    ).scalar_one_or_none() or ""

    if "third_party" not in schema_sql:
        raise RuntimeError(
            "Constraint source_type chưa cho phép third_party."
        )

    user_ids = list(
        session.execute(
            text("SELECT id FROM users ORDER BY id")
        ).scalars()
    )

    if requested_owner_id is not None:
        if requested_owner_id not in user_ids:
            raise ValueError(
                f"Không tìm thấy owner user ID={requested_owner_id}."
            )
        owner_id = requested_owner_id
    elif len(user_ids) == 1:
        owner_id = user_ids[0]
    else:
        raise ValueError(
            "Cần chỉ định --owner-user-id vì database không có "
            "đúng một user. Chưa có dữ liệu nào được nhập."
        )

    return owner_id


def existing_fingerprint(question: Question) -> str:
    options = {
        option.option_key: option.content
        for option in question.options
    }

    return content_fingerprint(
        question.part,
        question.content,
        options,
    )


def run_import(args: argparse.Namespace) -> None:
    input_path = args.input
    report_path = args.report

    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path

    if not report_path.is_absolute():
        report_path = PROJECT_ROOT / report_path

    records = load_staged_records(input_path)

    skipped_already_imported: list[str] = []
    skipped_duplicate_content: list[str] = []
    to_insert: list[dict[str, Any]] = []

    with SessionLocal() as session:
        with session.begin():
            owner_id = validate_database(
                session,
                args.owner_user_id,
            )

            existing_questions = session.query(Question).all()

            existing_records = [
                (question, existing_fingerprint(question))
                for question in existing_questions
            ]

            for record in records:
                source_matches = [
                    question
                    for question in existing_questions
                    if (
                        question.source_name == record["source_name"]
                        and question.source_reference
                        == record["source_reference"]
                    )
                ]

                if len(source_matches) > 1:
                    raise RuntimeError(
                        "Database có nhiều câu hỏi cùng source reference: "
                        f"{record['source_record_id']}"
                    )

                if source_matches:
                    existing = source_matches[0]

                    if (
                        existing_fingerprint(existing)
                        == record["fingerprint"]
                        and existing.correct_option_key
                        == record["correct_option_key"]
                    ):
                        skipped_already_imported.append(
                            record["source_record_id"]
                        )
                        continue

                    raise RuntimeError(
                        "Source reference đã tồn tại nhưng nội dung "
                        "hoặc đáp án khác. Không ghi đè: "
                        f"{record['source_record_id']}"
                    )

                duplicates = [
                    question
                    for question, fingerprint in existing_records
                    if fingerprint == record["fingerprint"]
                ]

                if duplicates:
                    if any(
                        question.correct_option_key
                        != record["correct_option_key"]
                        for question in duplicates
                    ):
                        raise RuntimeError(
                            "Nội dung trùng với câu hỏi hiện có nhưng "
                            "đáp án khác. Cần kiểm tra thủ công: "
                            f"{record['source_record_id']}"
                        )

                    skipped_duplicate_content.append(
                        record["source_record_id"]
                    )
                    continue

                to_insert.append(record)

            if args.apply:
                for record in to_insert:
                    question = Question(
                        owner_user_id=owner_id,
                        part=record["part"],
                        content=record["content"],
                        correct_option_key=record["correct_option_key"],
                        difficulty=record["difficulty"],
                        explanation=record["explanation"],
                        review_status="pending_review",
                        source_type="third_party",
                        source_name=record["source_name"],
                        source_reference=record["source_reference"],
                        source_license=record["source_license"],
                        usage_permission_status="unknown",
                        visibility="private",
                        content_hash=record["content_hash"],
                        options=[
                            QuestionOption(
                                option_key=key,
                                content=record["options"][key],
                            )
                            for key in OPTION_KEYS
                        ],
                    )

                    session.add(question)

                # Force database constraints to be checked before commit.
                session.flush()

    report = {
        "mode": "apply" if args.apply else "dry_run",
        "database": str(engine.url),
        "input_file": str(input_path),
        "migration_revision": EXPECTED_REVISION,
        "input_records": len(records),
        "would_insert": len(to_insert),
        "inserted": len(to_insert) if args.apply else 0,
        "skipped_already_imported": skipped_already_imported,
        "skipped_duplicate_content": skipped_duplicate_content,
        "owner_user_id": owner_id,
        "imported_source_type": "third_party",
        "imported_review_status": "pending_review",
        "imported_usage_permission_status": "unknown",
        "imported_visibility": "private",
        "content_license_policy": (
            "Use content_license only; do not infer content rights "
            "from repository_license."
        ),
        "candidate_source_record_ids": [
            record["source_record_id"] for record in to_insert
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Mode:", report["mode"])
    print("Database:", report["database"])
    print("Input records:", len(records))
    print("Would insert:", len(to_insert))
    print("Inserted:", report["inserted"])
    print("Skipped already imported:", len(skipped_already_imported))
    print("Skipped duplicate content:", len(skipped_duplicate_content))
    print("Owner user ID:", owner_id)
    print("Review status: pending_review")
    print("Usage permission status: unknown")
    print("Visibility: private")
    print("Report:", report_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely import staged TOEIC Part 5 questions."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Đường dẫn JSONL đầu vào.",
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Đường dẫn báo cáo importer.",
    )

    parser.add_argument(
        "--owner-user-id",
        type=int,
        default=None,
        help="User ID sở hữu câu hỏi private; tự nhận diện nếu DB chỉ có một user.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ghi dữ liệu thật. Nếu không có cờ này, chỉ chạy thử.",
    )

    args = parser.parse_args()

    try:
        run_import(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
