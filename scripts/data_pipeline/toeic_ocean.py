
from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SOURCE_NAME = "toeic-question-ocean"
SOURCE_URL = "https://github.com/kdeppaei/toeic-question-ocean"
REPOSITORY_LICENSE = "MIT"

OPTION_LABELS = ("A", "B", "C", "D")
ALLOWED_CORRECTION_FIELDS = {"answer", "explanation", "tags"}


def _skip_javascript_string_or_comment(
    source: str,
    index: int,
) -> int | None:
    """Skip a JavaScript string or comment without executing JavaScript."""
    char = source[index]

    if char in ("'", '"', "`"):
        quote = char
        index += 1

        while index < len(source):
            if source[index] == "\\":
                index += 2
            elif source[index] == quote:
                return index + 1
            else:
                index += 1

        return len(source)

    if source.startswith("//", index):
        newline = source.find("\n", index + 2)
        return len(source) if newline == -1 else newline + 1

    if source.startswith("/*", index):
        end = source.find("*/", index + 2)
        return len(source) if end == -1 else end + 2

    return None


def _looks_like_question(value: Any) -> bool:
    """Identify question records by their ID and required field names."""
    if not isinstance(value, dict):
        return False

    record_id = value.get("id")

    if not isinstance(record_id, str):
        return False

    if not re.fullmatch(r"P\d+-\d+", record_id.strip()):
        return False

    required_keys = {"part", "prompt", "choices", "answer"}
    return required_keys.issubset(value.keys())


def extract_question_records(source: str) -> list[dict[str, Any]]:
    """
    Extract JSON-compatible question objects from JavaScript source text.

    This function never executes the JavaScript source.
    """
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    index = 0

    while index < len(source):
        skipped_to = _skip_javascript_string_or_comment(source, index)

        if skipped_to is not None:
            index = skipped_to
            continue

        if source[index] != "{":
            index += 1
            continue

        try:
            value, end = decoder.raw_decode(source, index)
        except json.JSONDecodeError:
            index += 1
            continue

        if _looks_like_question(value):
            records.append(value)
            index = end
        else:
            # Continue scanning so nested question objects can be found.
            index += 1

    return records


def read_question_bank(path: str | Path) -> list[dict[str, Any]]:
    """Read a source file and extract its question records."""
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8-sig")
    return extract_question_records(source)


def load_correction_manifest(
    path: str | Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """
    Load verified corrections only.

    Only answer, explanation, and tags are allowed in the changes object.
    """
    manifest_path = Path(path)
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8-sig")
    )

    if not isinstance(manifest, dict):
        raise ValueError("Correction manifest must be a JSON object.")

    raw_corrections = manifest.get("corrections", {})

    if not isinstance(raw_corrections, dict):
        raise ValueError("'corrections' must be a JSON object.")

    accepted: dict[str, dict[str, Any]] = {}
    unverified: list[str] = []
    invalid: list[str] = []

    for record_id, entry in raw_corrections.items():
        if not isinstance(entry, dict):
            invalid.append(str(record_id))
            continue

        if entry.get("status") != "verified":
            unverified.append(str(record_id))
            continue

        changes = entry.get("changes", {})

        if not isinstance(changes, dict):
            invalid.append(str(record_id))
            continue

        clean_changes: dict[str, Any] = {}
        has_invalid_change = False

        for field, value in changes.items():
            if field not in ALLOWED_CORRECTION_FIELDS:
                continue

            if field == "answer":
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value not in range(4)
                ):
                    has_invalid_change = True
                    continue

            elif field == "explanation":
                if not isinstance(value, str) or not value.strip():
                    has_invalid_change = True
                    continue

            elif field == "tags":
                if (
                    not isinstance(value, list)
                    or not all(
                        isinstance(tag, str) for tag in value
                    )
                ):
                    has_invalid_change = True
                    continue

            clean_changes[field] = value

        if has_invalid_change:
            invalid.append(str(record_id))
            continue

        if clean_changes:
            accepted[str(record_id)] = clean_changes

    audit = {
        "unverified_corrections": sorted(unverified),
        "invalid_corrections": sorted(invalid),
    }

    return accepted, audit


def _parse_part(value: Any) -> int | None:
    """Convert values such as 5, '5', or 'Part 5' to an integer."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, str):
        match = re.search(r"\d+", value.strip())

        if match:
            return int(match.group())

    return None


def _normalize_text(value: Any) -> str:
    """Normalize whitespace and case for duplicate detection."""
    if not isinstance(value, str):
        return ""

    return re.sub(r"\s+", " ", value).strip().casefold()


def _normalize_record(
    raw: dict[str, Any],
    target_part: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate and normalize one source question."""
    errors: list[str] = []

    record_id = raw.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        errors.append("id must be a non-empty string")
        record_id = ""
    else:
        record_id = record_id.strip()

    parsed_part = _parse_part(raw.get("part"))

    if parsed_part is None:
        errors.append("part is missing or invalid")
    elif parsed_part != target_part:
        errors.append("part does not match target part")

    prompt = raw.get("prompt")

    if not isinstance(prompt, str) or not prompt.strip():
        errors.append("prompt must be a non-empty string")

    choices = raw.get("choices")

    if (
        not isinstance(choices, list)
        or len(choices) != 4
        or not all(
            isinstance(choice, str) and choice.strip()
            for choice in choices
        )
    ):
        errors.append("choices must contain exactly four non-empty strings")

    answer = raw.get("answer")

    if (
        not isinstance(answer, int)
        or isinstance(answer, bool)
        or answer not in range(4)
    ):
        errors.append("answer must be an integer from 0 to 3")

    explanation = raw.get("explanation")

    if (
        not isinstance(explanation, str)
        or not explanation.strip()
    ):
        errors.append("explanation must be a non-empty string")

    if errors:
        return None, errors

    options = {
        label: choice.strip()
        for label, choice in zip(OPTION_LABELS, choices)
    }

    raw_difficulty = raw.get("difficulty")

    if raw_difficulty is None:
        source_difficulty = None
    else:
        source_difficulty = str(raw_difficulty).strip() or None

    category = raw.get("category")
    source_category = (
        category.strip()
        if isinstance(category, str) and category.strip()
        else None
    )

    raw_tags = raw.get("tags")
    if isinstance(raw_tags, list):
        source_tags = [
            tag.strip()
            for tag in raw_tags
            if isinstance(tag, str) and tag.strip()
        ]
    else:
        source_tags = []

    normalized = {
        "schema_version": "1.0",
        "question_id": f"{SOURCE_NAME}:{record_id}",
        "source_name": SOURCE_NAME,
        "source_record_id": record_id,
        "part": target_part,
        "text": prompt.strip(),
        "options": options,
        "correct_option": OPTION_LABELS[answer],
        "explanation": explanation.strip(),
        "difficulty": None,
        "source_difficulty": source_difficulty,
        "source_category": source_category,
        "source_tags": source_tags,
        "skill_tags": [],
        "source_url": SOURCE_URL,
        "repository_license": REPOSITORY_LICENSE,
        "content_license": None,
        "rights_status": "unknown",
        "reviewed_status": "pending_review",
        "passage_id": None,
        "question_order": None,
    }

    return normalized, []


def _find_exact_duplicate_groups(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)

    for record in records:
        fingerprint = (
            _normalize_text(record["text"]),
            tuple(
                _normalize_text(record["options"][label])
                for label in OPTION_LABELS
            ),
        )
        groups[fingerprint].append(record)

    result = []

    for group in groups.values():
        if len(group) < 2:
            continue

        answers = {item["correct_option"] for item in group}

        result.append({
            "source_record_ids": [
                item["source_record_id"] for item in group
            ],
            "question_ids": [
                item["question_id"] for item in group
            ],
            "conflicting_answers": len(answers) > 1,
        })

    return result


def _find_near_duplicate_pairs(
    records: list[dict[str, Any]],
    threshold: float,
) -> list[dict[str, Any]]:
    result = []

    for index, first in enumerate(records):
        first_text = _normalize_text(first["text"])

        for second in records[index + 1:]:
            second_text = _normalize_text(second["text"])

            if not first_text or not second_text:
                continue

            if first_text == second_text:
                continue

            similarity = SequenceMatcher(
                None,
                first_text,
                second_text,
            ).ratio()

            if similarity >= threshold:
                result.append({
                    "source_record_id_1": first["source_record_id"],
                    "source_record_id_2": second["source_record_id"],
                    "similarity": round(similarity, 4),
                })

    return result


def build_staging_records(
    raw_records: list[dict[str, Any]],
    corrections: dict[str, dict[str, Any]] | None = None,
    part: int = 5,
    near_duplicate_threshold: float = 0.90,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Normalize source records for staging.

    Invalid records are rejected. Exact and near duplicates are reported,
    not automatically deleted. Source records are never mutated.
    """
    if not 0 <= near_duplicate_threshold <= 1:
        raise ValueError(
            "near_duplicate_threshold must be between 0 and 1."
        )

    corrections = corrections or {}

    candidates: list[dict[str, Any]] = []
    rejected_records: list[dict[str, Any]] = []
    skipped_non_target_part = 0

    for raw in raw_records:
        if not isinstance(raw, dict):
            rejected_records.append({
                "source_record_id": None,
                "errors": ["record must be a JSON object"],
            })
            continue

        parsed_part = _parse_part(raw.get("part"))

        if parsed_part is not None and parsed_part != part:
            skipped_non_target_part += 1
            continue

        candidates.append(raw)

    id_counts = Counter(
        raw.get("id", "").strip()
        for raw in candidates
        if isinstance(raw.get("id"), str) and raw.get("id").strip()
    )

    duplicate_source_ids = sorted(
        record_id
        for record_id, count in id_counts.items()
        if count > 1
    )

    normalized_records: list[dict[str, Any]] = []
    corrections_applied: list[str] = []

    for raw in candidates:
        source_record_id = raw.get("id")

        if isinstance(source_record_id, str):
            source_record_id = source_record_id.strip()
        else:
            source_record_id = None

        if source_record_id in duplicate_source_ids:
            rejected_records.append({
                "source_record_id": source_record_id,
                "errors": ["duplicate source_record_id"],
            })
            continue

        working_record = copy.deepcopy(raw)

        if source_record_id in corrections:
            changes = corrections[source_record_id]

            if isinstance(changes, dict):
                for field, value in changes.items():
                    if field in ALLOWED_CORRECTION_FIELDS:
                        working_record[field] = copy.deepcopy(value)

                corrections_applied.append(source_record_id)

        normalized, errors = _normalize_record(
            working_record,
            target_part=part,
        )

        if errors:
            rejected_records.append({
                "source_record_id": source_record_id,
                "errors": errors,
            })
            continue

        if normalized is not None:
            normalized_records.append(normalized)

    report = {
        "source_name": SOURCE_NAME,
        "target_part": part,
        "input_records_count": len(raw_records),
        "valid_records_count": len(normalized_records),
        "rejected_records_count": len(rejected_records),
        "rejected_records": rejected_records,
        "skipped_non_target_part": skipped_non_target_part,
        "duplicate_source_ids": duplicate_source_ids,
        "corrections_applied": sorted(set(corrections_applied)),
        "exact_duplicate_groups": _find_exact_duplicate_groups(
            normalized_records
        ),
        "near_duplicate_pairs": _find_near_duplicate_pairs(
            normalized_records,
            threshold=near_duplicate_threshold,
        ),
    }

    return normalized_records, report


def run_pipeline(
    input_path: str | Path,
    output_path: str | Path,
    report_path: str | Path,
    corrections_path: str | Path | None = None,
    part: int = 5,
    near_duplicate_threshold: float = 0.90,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the read-only extraction, validation, and staging pipeline."""
    raw_records = read_question_bank(input_path)

    corrections: dict[str, dict[str, Any]] = {}
    correction_audit: dict[str, Any] = {
        "unverified_corrections": [],
        "invalid_corrections": [],
    }

    if corrections_path is not None:
        corrections, correction_audit = load_correction_manifest(
            corrections_path
        )

    records, report = build_staging_records(
        raw_records,
        corrections=corrections,
        part=part,
        near_duplicate_threshold=near_duplicate_threshold,
    )

    report["input_file"] = str(input_path)
    report["output_file"] = str(output_path)
    report["correction_audit"] = correction_audit

    output = Path(output_path)
    report_file = Path(report_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return records, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare TOEIC Question Ocean records for staging."
    )

    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--corrections")
    parser.add_argument("--part", type=int, default=5)
    parser.add_argument(
        "--near-duplicate-threshold",
        type=float,
        default=0.90,
    )

    args = parser.parse_args()

    records, report = run_pipeline(
        input_path=args.input,
        output_path=args.output,
        report_path=args.report,
        corrections_path=args.corrections,
        part=args.part,
        near_duplicate_threshold=args.near_duplicate_threshold,
    )

    print(f"Input records: {report['input_records_count']}")
    print(f"Staged records: {len(records)}")
    print(f"Rejected records: {report['rejected_records_count']}")
    print(
        "Exact duplicate groups:",
        len(report["exact_duplicate_groups"]),
    )
    print(
        "Near duplicate pairs:",
        len(report["near_duplicate_pairs"]),
    )
    print(f"Output: {args.output}")
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
