
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from backend.app.db.session import engine


EXPECTED_REVISION = "55db8077d91e"

DEFAULT_INPUT = Path("data/processed/toeic-ocean-part5.jsonl")
DEFAULT_MANIFEST = Path(
    "docs/data-pipeline/toeic-ocean-skill-mapping.json"
)
DEFAULT_REPORT = Path(
    "data/processed/toeic-ocean-skill-mapping-report.json"
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL không hợp lệ tại dòng {line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Bản ghi dòng {line_number} phải là JSON object."
                )

            record_id = str(
                record.get("source_record_id", "")
            ).strip()
            source_url = str(
                record.get("source_url", "")
            ).strip()

            if not record_id or not source_url:
                raise ValueError(
                    f"Dòng {line_number} thiếu source_record_id "
                    "hoặc source_url."
                )

            if record_id in seen_ids:
                raise ValueError(
                    f"source_record_id bị trùng: {record_id}"
                )

            tags = record.get("source_tags", [])
            if not isinstance(tags, list):
                raise ValueError(
                    f"source_tags phải là list: {record_id}"
                )

            seen_ids.add(record_id)
            records.append(record)

    if not records:
        raise ValueError("JSONL không có bản ghi nào.")

    return records


def load_manifest(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)

    if manifest.get("schema_version") != "1.0":
        raise ValueError("schema_version của manifest không hợp lệ.")

    mapping = manifest.get("tag_to_skill")
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Manifest thiếu tag_to_skill hợp lệ.")

    result: dict[str, str] = {}

    for tag, skill_code in mapping.items():
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("Manifest có tag rỗng hoặc không hợp lệ.")

        if not isinstance(skill_code, str) or not skill_code.strip():
            raise ValueError(
                f"Skill code không hợp lệ cho tag {tag!r}."
            )

        result[tag.strip().lower()] = skill_code.strip()

    return result


def build_mapping_plan(
    records: list[dict[str, Any]],
    tag_to_skill: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int]]:
    plan: list[dict[str, Any]] = []
    unmapped_counts: Counter[str] = Counter()
    links_by_skill: Counter[str] = Counter()

    for record in records:
        tags = {
            str(tag).strip().lower()
            for tag in record.get("source_tags", [])
            if str(tag).strip()
        }

        mapped_tags = sorted(
            tag for tag in tags if tag in tag_to_skill
        )
        unmapped_tags = sorted(
            tag for tag in tags if tag not in tag_to_skill
        )

        skill_codes = sorted({
            tag_to_skill[tag] for tag in mapped_tags
        })

        unmapped_counts.update(unmapped_tags)
        links_by_skill.update(skill_codes)

        source_record_id = str(record["source_record_id"])
        source_url = str(record["source_url"]).rstrip("/")

        plan.append({
            "source_record_id": source_record_id,
            "source_reference": (
                f"{source_url}#record={source_record_id}"
            ),
            "skill_codes": skill_codes,
            "unmapped_tags": unmapped_tags,
        })

    return plan, dict(unmapped_counts), dict(links_by_skill)


def get_database_path() -> Path:
    database = engine.url.database

    if not database or database == ":memory:":
        raise ValueError(
            "Chỉ hỗ trợ SQLite database dạng file cho script này."
        )

    path = Path(database)

    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.is_file():
        raise ValueError(f"Không tìm thấy database: {path}")

    return path


def check_database(conn: sqlite3.Connection) -> str:
    conn.execute("PRAGMA foreign_keys = ON")

    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise ValueError("Không bật được SQLite foreign keys.")

    revision_row = conn.execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()

    if not revision_row:
        raise ValueError("Không tìm thấy Alembic revision.")

    revision = revision_row[0]

    if revision != EXPECTED_REVISION:
        raise ValueError(
            f"Revision không đúng: {revision}; "
            f"yêu cầu {EXPECTED_REVISION}."
        )

    required_tables = {
        "questions",
        "skills",
        "question_skills",
    }

    actual_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    missing = required_tables - actual_tables
    if missing:
        raise ValueError(
            f"Database thiếu bảng: {sorted(missing)}"
        )

    return revision


def run_mapping(
    input_path: Path,
    manifest_path: Path,
    report_path: Path,
    apply: bool = False,
) -> dict[str, Any]:
    records = load_jsonl(input_path)
    tag_to_skill = load_manifest(manifest_path)

    plan, unmapped_counts, links_by_skill = build_mapping_plan(
        records, tag_to_skill
    )

    db_path = get_database_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        revision = check_database(conn)

        skill_rows = conn.execute(
            "SELECT id, code FROM skills"
        ).fetchall()
        skill_id_by_code = {
            row["code"]: row["id"] for row in skill_rows
        }

        missing_codes = set(tag_to_skill.values()) - set(
            skill_id_by_code
        )
        if missing_codes:
            raise ValueError(
                "Manifest tham chiếu kỹ năng chưa tồn tại: "
                f"{sorted(missing_codes)}"
            )

        resolved: list[dict[str, Any]] = []

        for item in plan:
            rows = conn.execute(
                """
                SELECT id, source_type, review_status,
                       usage_permission_status, visibility
                FROM questions
                WHERE source_reference = ?
                """,
                (item["source_reference"],),
            ).fetchall()

            if len(rows) != 1:
                raise ValueError(
                    f"{item['source_record_id']}: cần đúng 1 câu hỏi "
                    f"khớp source_reference, tìm thấy {len(rows)}."
                )

            question = rows[0]

            if question["source_type"] != "third_party":
                raise ValueError(
                    f"{item['source_record_id']}: source_type "
                    "không phải third_party."
                )

            if (
                question["review_status"] != "pending_review"
                or question["usage_permission_status"] != "unknown"
                or question["visibility"] != "private"
            ):
                raise ValueError(
                    f"{item['source_record_id']}: trạng thái câu hỏi "
                    "không đúng trạng thái an toàn dự kiến."
                )

            question_id = question["id"]

            existing_ids = {
                row["skill_id"]
                for row in conn.execute(
                    """
                    SELECT skill_id
                    FROM question_skills
                    WHERE question_id = ?
                    """,
                    (question_id,),
                )
            }

            existing_codes = {
                code
                for code, skill_id in skill_id_by_code.items()
                if skill_id in existing_ids
            }

            new_codes = [
                code for code in item["skill_codes"]
                if code not in existing_codes
            ]

            resolved.append({
                **item,
                "question_db_id": question_id,
                "existing_mapped_skills": sorted(
                    set(item["skill_codes"]) & existing_codes
                ),
                "new_skill_codes": new_codes,
            })

        pairs_to_insert = [
            (item["question_db_id"], skill_id_by_code[code])
            for item in resolved
            for code in item["new_skill_codes"]
        ]

        inserted = 0

        if apply:
            conn.execute("BEGIN IMMEDIATE")

            for question_id, skill_id in pairs_to_insert:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO question_skills
                        (question_id, skill_id)
                    VALUES (?, ?)
                    """,
                    (question_id, skill_id),
                )
                inserted += max(cursor.rowcount, 0)

            violations = list(
                conn.execute("PRAGMA foreign_key_check")
            )
            if violations:
                raise ValueError(
                    "Phát hiện lỗi khóa ngoại sau khi ánh xạ: "
                    f"{violations[:10]}"
                )

            conn.commit()

        report = {
            "mode": "apply" if apply else "dry_run",
            "database": str(db_path),
            "alembic_revision": revision,
            "input_records": len(records),
            "questions_with_mapped_skill": sum(
                bool(item["skill_codes"]) for item in resolved
            ),
            "questions_without_mapped_skill": sum(
                not item["skill_codes"] for item in resolved
            ),
            "would_insert_links": len(pairs_to_insert),
            "inserted_links": inserted,
            "unmapped_tag_counts": unmapped_counts,
            "planned_links_by_skill": links_by_skill,
            "question_mappings": resolved,
        }

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return report

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map TOEIC Question Ocean tags to existing skills."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ghi liên kết vào question_skills. Mặc định chỉ dry-run.",
    )
    args = parser.parse_args()

    try:
        report = run_mapping(
            args.input,
            args.manifest,
            args.report,
            apply=args.apply,
        )
    except (ValueError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Mode: {report['mode']}")
    print(f"Database: {report['database']}")
    print(f"Input records: {report['input_records']}")
    print(
        "Questions with mapped skill: "
        f"{report['questions_with_mapped_skill']}"
    )
    print(
        "Questions without mapped skill: "
        f"{report['questions_without_mapped_skill']}"
    )
    print(f"Would insert links: {report['would_insert_links']}")
    print(f"Inserted links: {report['inserted_links']}")
    print(
        "Planned links by skill: "
        f"{json.dumps(report['planned_links_by_skill'], ensure_ascii=False)}"
    )
    print(
        "Unmapped tags: "
        f"{json.dumps(report['unmapped_tag_counts'], ensure_ascii=False)}"
    )
    print(f"Report: {args.report.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
