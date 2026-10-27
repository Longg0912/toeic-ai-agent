
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = ROOT / "data" / "processed" / "toeic-ocean-part5.jsonl"
DEFAULT_DATABASE = ROOT / "data" / "toeic.sqlite3"
DEFAULT_MANIFEST = (
    ROOT / "docs" / "data-pipeline" / "toeic-ocean-skill-mapping.json"
)
DEFAULT_REPORT = (
    ROOT / "data" / "processed" / "toeic-ocean-skill-audit-report.json"
)

EXPECTED_REVISION = "55db8077d91e"

GENERIC_TAGS = {"grammar", "reading", "vocabulary"}

REQUIRED_TABLES = {
    "alembic_version",
    "questions",
    "question_options",
    "question_skills",
    "skills",
}


def normalize_text(value: Any) -> str:
    """Chuẩn hóa khoảng trắng để so sánh nội dung."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def normalize_tags(value: Any) -> list[str]:
    """Chuẩn hóa tag, bỏ tag rỗng và loại bỏ tag trùng trong một câu."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []

    result = []
    seen = set()

    for item in values:
        if not isinstance(item, str):
            continue

        tag = item.strip().lower()

        if tag and tag not in seen:
            result.append(tag)
            seen.add(tag)

    return result


def normalize_options(value: Any) -> list[dict[str, str]]:
    """
    Chuẩn hóa options từ dict hoặc list thành:
    [{"key": "A", "text": "..."}, ...]
    """
    result = []

    if isinstance(value, dict):
        items = list(value.items())

        for index, (key, item) in enumerate(items):
            if isinstance(item, dict):
                option_key = (
                    item.get("key")
                    or item.get("option_key")
                    or item.get("label")
                    or key
                )
                option_text = (
                    item.get("text")
                    or item.get("content")
                    or item.get("value")
                    or ""
                )
            else:
                option_key = key
                option_text = item

            result.append(
                {
                    "key": str(option_key).strip().upper(),
                    "text": normalize_text(option_text),
                }
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            fallback_key = chr(ord("A") + index)

            if isinstance(item, dict):
                option_key = (
                    item.get("key")
                    or item.get("option_key")
                    or item.get("label")
                    or fallback_key
                )
                option_text = (
                    item.get("text")
                    or item.get("content")
                    or item.get("value")
                    or ""
                )
            else:
                option_key = fallback_key
                option_text = item

            result.append(
                {
                    "key": str(option_key).strip().upper(),
                    "text": normalize_text(option_text),
                }
            )

    return sorted(result, key=lambda item: item["key"])


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Đọc JSONL và kiểm tra ID nguồn."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file đầu vào: {path}")

    records = []
    seen_ids = set()

    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL lỗi tại dòng {line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Dòng {line_number} không chứa JSON object."
                )

            record_id = record.get("source_record_id")
            source_url = record.get("source_url")

            if not record_id or not source_url:
                raise ValueError(
                    f"Dòng {line_number} thiếu source_record_id "
                    "hoặc source_url."
                )

            record_id = str(record_id)

            if record_id in seen_ids:
                raise ValueError(
                    f"source_record_id bị trùng: {record_id}"
                )

            seen_ids.add(record_id)
            record["source_tags"] = normalize_tags(
                record.get("source_tags")
            )
            record["skill_tags"] = normalize_tags(
                record.get("skill_tags")
            )
            records.append(record)

    return records


def load_manifest(path: Path) -> dict[str, str]:
    """Đọc manifest ánh xạ tag sang mã kỹ năng."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy manifest: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Manifest phải là một JSON object.")

    raw_mapping = data.get("tag_to_skill")

    if not isinstance(raw_mapping, dict):
        raise ValueError("Manifest thiếu object tag_to_skill.")

    mapping = {}

    for tag, skill_code in raw_mapping.items():
        normalized_tag = str(tag).strip().lower()
        normalized_code = str(skill_code).strip()

        if normalized_tag and normalized_code:
            mapping[normalized_tag] = normalized_code

    return mapping


def connect_readonly(database_path: Path) -> sqlite3.Connection:
    """
    Mở SQLite ở chế độ chỉ đọc.

    mode=ro ngăn ghi database; query_only là lớp bảo vệ bổ sung.
    """
    path = database_path.expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy database: {path}")

    connection = sqlite3.connect(
        path.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    return connection


def read_database_metadata(
    connection: sqlite3.Connection,
) -> dict[str, Any]:
    """Kiểm tra schema và tính toàn vẹn bằng các truy vấn chỉ đọc."""
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    missing_tables = sorted(REQUIRED_TABLES - tables)

    if missing_tables:
        raise ValueError(
            f"Database thiếu bảng cần thiết: {missing_tables}"
        )

    revision_row = connection.execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()

    revision = revision_row["version_num"] if revision_row else None

    if revision != EXPECTED_REVISION:
        raise ValueError(
            f"Revision database là {revision!r}, "
            f"nhưng script đang yêu cầu {EXPECTED_REVISION!r}. "
            "Dừng kiểm kê để tránh đọc sai schema."
        )

    integrity = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    foreign_key_violations = [
        list(row)
        for row in connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    ]

    skills = [
        dict(row)
        for row in connection.execute(
            "SELECT code, name, category FROM skills ORDER BY code"
        ).fetchall()
    ]

    return {
        "revision": revision,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_key_violations,
        "skills": skills,
    }


def build_tag_inventory(
    records: list[dict[str, Any]],
    tag_to_skill: dict[str, str],
    available_skill_codes: set[str],
) -> list[dict[str, Any]]:
    """Thống kê tag, tình trạng ánh xạ và ví dụ câu hỏi."""
    counts = Counter()
    examples = defaultdict(list)

    for record in records:
        record_id = str(record["source_record_id"])
        text = normalize_text(record.get("text"))

        for tag in normalize_tags(record.get("source_tags")):
            counts[tag] += 1

            if len(examples[tag]) < 5:
                examples[tag].append(
                    {
                        "source_record_id": record_id,
                        "text": text[:180],
                    }
                )

    inventory = []

    for tag, count in sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        mapped_code = tag_to_skill.get(tag)

        if mapped_code:
            if mapped_code in available_skill_codes:
                classification = "mapped_to_skill"
            else:
                classification = "mapped_skill_missing_from_database"
        elif tag in GENERIC_TAGS:
            classification = "generic_needs_review"
        else:
            classification = "needs_review"

        inventory.append(
            {
                "tag": tag,
                "occurrences": count,
                "classification": classification,
                "mapped_skill_code": mapped_code,
                "examples": examples[tag],
            }
        )

    return inventory


def read_question_options(
    connection: sqlite3.Connection,
    question_id: int,
) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT option_key, content
        FROM question_options
        WHERE question_id = ?
        ORDER BY option_key
        """,
        (question_id,),
    ).fetchall()

    return [
        {
            "key": str(row["option_key"]).strip().upper(),
            "text": normalize_text(row["content"]),
        }
        for row in rows
    ]


def read_question_skills(
    connection: sqlite3.Connection,
    question_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT DISTINCT s.code, s.name, s.category
        FROM question_skills AS qs
        JOIN skills AS s ON s.id = qs.skill_id
        WHERE qs.question_id = ?
        ORDER BY s.code
        """,
        (question_id,),
    ).fetchall()

    return [dict(row) for row in rows]


def build_audit_report(
    records: list[dict[str, Any]],
    tag_to_skill: dict[str, str],
    connection: sqlite3.Connection,
    database_path: Path,
) -> dict[str, Any]:
    """Tạo báo cáo từ JSONL và snapshot database chỉ đọc."""
    metadata = read_database_metadata(connection)
    available_skill_codes = {
        skill["code"] for skill in metadata["skills"]
    }

    question_inventory = []
    questions_without_skills = []
    records_not_found = []
    records_with_multiple_matches = []

    comparison_fields = [
        "text_matches_database",
        "options_match_database",
        "correct_option_matches_database",
        "explanation_matches_database",
    ]
    comparison_mismatches = Counter()
    records_with_content_mismatch = 0

    tag_occurrences = Counter()
    questions_with_unmapped_tags = 0
    mapped_tag_occurrences = 0
    nonempty_skill_tags = 0

    rights_counts = Counter()
    review_counts = Counter()

    for record in records:
        record_id = str(record["source_record_id"])
        source_reference = (
            str(record["source_url"]).rstrip("/")
            + "#record="
            + record_id
        )

        source_tags = normalize_tags(record.get("source_tags"))
        source_skill_tags = normalize_tags(record.get("skill_tags"))

        if source_skill_tags:
            nonempty_skill_tags += 1

        for tag in source_tags:
            tag_occurrences[tag] += 1

            if tag in tag_to_skill:
                mapped_tag_occurrences += 1

        unmapped_tags = [
            tag for tag in source_tags if tag not in tag_to_skill
        ]

        if unmapped_tags:
            questions_with_unmapped_tags += 1

        mapped_skill_codes = sorted(
            {
                tag_to_skill[tag]
                for tag in source_tags
                if tag in tag_to_skill
            }
        )

        rows = connection.execute(
            """
            SELECT
                id,
                part,
                content,
                correct_option_key,
                explanation,
                difficulty,
                source_type,
                source_license,
                review_status,
                usage_permission_status,
                visibility
            FROM questions
            WHERE source_reference = ?
            """,
            (source_reference,),
        ).fetchall()

        db_question_id = None
        linked_skill_codes = []
        missing_skill_links = []
        db_question = None
        db_options = []
        db_skills = []
        comparisons = None

        if len(rows) == 0:
            match_status = "not_found"
            records_not_found.append(
                {
                    "source_record_id": record_id,
                    "source_reference": source_reference,
                }
            )

        elif len(rows) > 1:
            match_status = "multiple"
            records_with_multiple_matches.append(
                {
                    "source_record_id": record_id,
                    "source_reference": source_reference,
                    "question_db_ids": [row["id"] for row in rows],
                }
            )

        else:
            match_status = "matched"
            db_question = dict(rows[0])
            db_question_id = db_question["id"]

            db_options = read_question_options(
                connection, db_question_id
            )
            db_skills = read_question_skills(
                connection, db_question_id
            )
            linked_skill_codes = [
                skill["code"] for skill in db_skills
            ]

            missing_skill_links = sorted(
                set(mapped_skill_codes) - set(linked_skill_codes)
            )

            source_options = normalize_options(
                record.get("options")
            )

            comparisons = {
                "text_matches_database": (
                    normalize_text(record.get("text"))
                    == normalize_text(db_question["content"])
                ),
                "options_match_database": (
                    source_options == db_options
                ),
                "correct_option_matches_database": (
                    normalize_text(record.get("correct_option")).upper()
                    == normalize_text(
                        db_question["correct_option_key"]
                    ).upper()
                ),
                "explanation_matches_database": (
                    normalize_text(record.get("explanation"))
                    == normalize_text(db_question["explanation"])
                ),
            }

            any_mismatch = False

            for field in comparison_fields:
                if not comparisons[field]:
                    comparison_mismatches[field] += 1
                    any_mismatch = True

            if any_mismatch:
                records_with_content_mismatch += 1

        if match_status == "matched" and not linked_skill_codes:
            classification_status = "unclassified"
        elif match_status == "matched":
            classification_status = "classified"
        else:
            classification_status = match_status

        entry = {
            "source_record_id": record_id,
            "source_reference": source_reference,
            "database_match_status": match_status,
            "question_db_id": db_question_id,
            "classification_status": classification_status,
            "text": normalize_text(record.get("text")),
            "options": normalize_options(record.get("options")),
            "correct_option": record.get("correct_option"),
            "explanation": record.get("explanation"),
            "source_tags": source_tags,
            "skill_tags": source_skill_tags,
            "mapped_skill_codes_from_tags": mapped_skill_codes,
            "unmapped_tags": unmapped_tags,
            "linked_skill_codes": linked_skill_codes,
            "mapped_skill_links_missing_in_database": (
                missing_skill_links
            ),
            "source_category": record.get("source_category"),
            "source_difficulty": record.get("source_difficulty"),
            "repository_license": record.get("repository_license"),
            "content_license": record.get("content_license"),
            "rights_status": record.get("rights_status", "unknown"),
            "reviewed_status": record.get(
                "reviewed_status", "pending_review"
            ),
            "database": (
                {
                    "content": db_question["content"],
                    "options": db_options,
                    "correct_option_key": (
                        db_question["correct_option_key"]
                    ),
                    "explanation": db_question["explanation"],
                    "source_type": db_question["source_type"],
                    "source_license": db_question["source_license"],
                    "review_status": db_question["review_status"],
                    "usage_permission_status": (
                        db_question["usage_permission_status"]
                    ),
                    "visibility": db_question["visibility"],
                    "linked_skills": db_skills,
                }
                if db_question is not None
                else None
            ),
            "content_comparison": comparisons,
        }

        question_inventory.append(
            {
                "source_record_id": record_id,
                "question_db_id": db_question_id,
                "database_match_status": match_status,
                "classification_status": classification_status,
                "source_tags": source_tags,
                "unmapped_tags": unmapped_tags,
                "linked_skill_codes": linked_skill_codes,
                "mapped_skill_links_missing_in_database": (
                    missing_skill_links
                ),
                "content_comparison": comparisons,
            }
        )

        if classification_status == "unclassified":
            questions_without_skills.append(entry)

        rights_counts[str(entry["rights_status"])] += 1
        review_counts[str(entry["reviewed_status"])] += 1

    tag_inventory = build_tag_inventory(
        records,
        tag_to_skill,
        available_skill_codes,
    )

    unclassified_count = len(questions_without_skills)
    classified_count = sum(
        item["classification_status"] == "classified"
        for item in question_inventory
    )

    unmapped_tag_counts = {
        item["tag"]: item["occurrences"]
        for item in tag_inventory
        if item["classification"] != "mapped_to_skill"
    }

    return {
        "report_type": "toeic_ocean_skill_audit",
        "mode": "read_only",
        "database": {
            "path": str(database_path.resolve()),
            "read_only": True,
            "alembic_revision": metadata["revision"],
            "integrity_check": metadata["integrity_check"],
            "foreign_key_violations": (
                metadata["foreign_key_violations"]
            ),
        },
        "summary": {
            "input_records": len(records),
            "database_matches": sum(
                item["database_match_status"] == "matched"
                for item in question_inventory
            ),
            "records_not_found_in_database": len(records_not_found),
            "records_with_multiple_database_matches": len(
                records_with_multiple_matches
            ),
            "questions_with_mapped_skill": classified_count,
            "questions_without_mapped_skill": unclassified_count,
            "questions_with_unmapped_tags": (
                questions_with_unmapped_tags
            ),
            "questions_with_nonempty_skill_tags": nonempty_skill_tags,
            "unique_source_tags": len(tag_inventory),
            "source_tag_occurrences": sum(tag_occurrences.values()),
            "mapped_tag_occurrences": mapped_tag_occurrences,
            "unmapped_tag_occurrences": (
                sum(tag_occurrences.values()) - mapped_tag_occurrences
            ),
            "records_with_content_mismatch": (
                records_with_content_mismatch
            ),
            "content_mismatch_counts": dict(comparison_mismatches),
            "rights_status_counts": dict(rights_counts),
            "reviewed_status_counts": dict(review_counts),
            "unmapped_tag_counts": unmapped_tag_counts,
        },
        "available_skills": metadata["skills"],
        "tag_inventory": tag_inventory,
        "question_inventory": question_inventory,
        "questions_without_skills": questions_without_skills,
        "records_not_found_in_database": records_not_found,
        "records_with_multiple_database_matches": (
            records_with_multiple_matches
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kiểm kê tag và câu hỏi TOEIC chưa được phân loại. "
            "Database được mở ở chế độ chỉ đọc."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)

    args = parser.parse_args()

    try:
        records = load_jsonl(args.input)
        tag_to_skill = load_manifest(args.manifest)

        connection = connect_readonly(args.database)

        try:
            report = build_audit_report(
                records,
                tag_to_skill,
                connection,
                args.database,
            )
        finally:
            connection.close()

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        summary = report["summary"]

        print("Mode: read_only")
        print(f"Database: {report['database']['path']}")
        print(f"Input records: {summary['input_records']}")
        print(
            "Questions with mapped skill: "
            f"{summary['questions_with_mapped_skill']}"
        )
        print(
            "Questions without mapped skill: "
            f"{summary['questions_without_mapped_skill']}"
        )
        print(f"Unique source tags: {summary['unique_source_tags']}")
        print(
            "Records not found in database: "
            f"{summary['records_not_found_in_database']}"
        )
        print(
            "Content mismatch records: "
            f"{summary['records_with_content_mismatch']}"
        )
        print(f"Report: {args.report.resolve()}")

        return 0

    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
