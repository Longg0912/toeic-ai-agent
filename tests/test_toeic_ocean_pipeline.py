import json

from scripts.data_pipeline.toeic_ocean import (
    build_staging_records,
    extract_question_records,
    load_correction_manifest,
)


def make_record(
    record_id="P5-001",
    part="5",
    prompt="The manager will review the report tomorrow.",
    choices=None,
    answer=1,
    explanation="The sentence uses the correct verb form.",
    difficulty="600",
    category="Verb forms",
    tags=None,
):
    return {
        "id": record_id,
        "part": part,
        "prompt": prompt,
        "choices": choices or [
            "review",
            "reviews",
            "reviewed",
            "reviewing",
        ],
        "answer": answer,
        "explanation": explanation,
        "difficulty": difficulty,
        "category": category,
        "tags": (
            tags
            if tags is not None
            else ["grammar", "reading"]
        ),
    }


def test_extracts_question_without_running_javascript():
    record = make_record()

    source = (
        "const QUESTION_BANK = ["
        + json.dumps(record)
        + "];\n"
        + 'throw new Error("this must never execute");'
    )

    extracted = extract_question_records(source)

    assert len(extracted) == 1
    assert extracted[0]["id"] == "P5-001"


def test_normalizes_answer_and_keeps_rights_pending():
    records, report = build_staging_records([
        make_record(answer=2)
    ])

    assert len(records) == 1
    assert records[0]["correct_option"] == "C"
    assert records[0]["difficulty"] is None
    assert records[0]["source_difficulty"] == "600"
    assert records[0]["rights_status"] == "unknown"
    assert records[0]["reviewed_status"] == "pending_review"
    assert records[0]["skill_tags"] == []
    assert report["rejected_records_count"] == 0


def test_skips_non_target_parts():
    records, report = build_staging_records([
        make_record(record_id="P5-001", part="5"),
        make_record(record_id="P6-001", part="6"),
    ])

    assert len(records) == 1
    assert records[0]["source_record_id"] == "P5-001"
    assert report["skipped_non_target_part"] == 1
    assert report["rejected_records_count"] == 0


def test_rejects_invalid_answer_and_missing_explanation():
    invalid = make_record(
        answer=4,
        explanation="",
    )

    records, report = build_staging_records([invalid])

    assert records == []
    assert report["rejected_records_count"] == 1

    errors = report["rejected_records"][0]["errors"]

    assert any("answer" in error for error in errors)
    assert any("explanation" in error for error in errors)


def test_verified_correction_is_applied_without_mutating_source():
    source_record = make_record(
        record_id="P5-073",
        answer=2,
    )

    records, report = build_staging_records(
        [source_record],
        corrections={
            "P5-073": {
                "answer": 1,
            }
        },
    )

    assert records[0]["correct_option"] == "B"
    assert source_record["answer"] == 2
    assert report["corrections_applied"] == ["P5-073"]


def test_exact_duplicates_are_reported_not_deleted():
    records, report = build_staging_records([
        make_record(record_id="P5-001"),
        make_record(record_id="P5-002"),
    ])

    assert len(records) == 2
    assert len(report["exact_duplicate_groups"]) == 1

    assert (
        report["exact_duplicate_groups"][0]["conflicting_answers"]
        is False
    )


def test_near_duplicates_are_reported_separately():
    first = make_record(
        record_id="P5-001",
        prompt="The manager will review the report tomorrow.",
    )

    second = make_record(
        record_id="P5-002",
        prompt="The manager will review the report tomorrow morning.",
    )

    records, report = build_staging_records(
        [first, second],
        near_duplicate_threshold=0.80,
    )

    assert len(records) == 2
    assert len(report["near_duplicate_pairs"]) >= 1


def test_duplicate_source_ids_are_rejected():
    records, report = build_staging_records([
        make_record(
            record_id="P5-001",
            prompt="Question one.",
        ),
        make_record(
            record_id="P5-001",
            prompt="Question two.",
        ),
    ])

    assert records == []
    assert report["duplicate_source_ids"] == ["P5-001"]
    assert report["rejected_records_count"] == 2


def test_loads_only_verified_corrections(tmp_path):
    manifest = {
        "schema_version": "1.0",
        "corrections": {
            "P5-073": {
                "status": "verified",
                "changes": {
                    "answer": 1,
                },
            },
            "P5-074": {
                "status": "pending_review",
                "changes": {
                    "answer": 0,
                },
            },
        },
    }

    path = tmp_path / "corrections.json"

    path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    corrections, audit = load_correction_manifest(path)

    assert corrections == {
        "P5-073": {
            "answer": 1,
        }
    }

    assert audit["unverified_corrections"] == ["P5-074"]