
import pytest

from scripts.data_pipeline.import_toeic_ocean import (
    content_fingerprint,
    prepare_record,
)


def sample_record():
    return {
        "question_id": "toeic-question-ocean:P5-001",
        "source_record_id": "P5-001",
        "part": 5,
        "text": "All reports must be submitted _____ Friday.",
        "options": {
            "A": "at",
            "B": "by",
            "C": "in",
            "D": "onward",
        },
        "correct_option": "B",
        "difficulty": None,
        "explanation": "Example explanation.",
        "source_name": "toeic-question-ocean",
        "source_url": (
            "https://github.com/kdeppaei/toeic-question-ocean"
        ),
        "content_license": None,
        "repository_license": "MIT",
        "reviewed_status": "pending_review",
        "rights_status": "unknown",
    }


def test_prepare_record_keeps_content_license_unknown():
    prepared = prepare_record(sample_record())

    assert prepared["source_record_id"] == "P5-001"
    assert prepared["correct_option_key"] == "B"
    assert prepared["source_license"] is None
    assert len(prepared["content_hash"]) == 64
    assert prepared["source_reference"].endswith("#record=P5-001")


def test_rejects_invalid_answer_key():
    record = sample_record()
    record["correct_option"] = "E"

    with pytest.raises(ValueError, match="đáp án đúng"):
        prepare_record(record)


def test_rejects_missing_option():
    record = sample_record()
    del record["options"]["D"]

    with pytest.raises(ValueError, match="đủ A, B, C, D"):
        prepare_record(record)


def test_rejects_records_not_pending_review():
    record = sample_record()
    record["reviewed_status"] = "approved"

    with pytest.raises(ValueError, match="pending_review"):
        prepare_record(record)


def test_rejects_rights_status_other_than_unknown():
    record = sample_record()
    record["rights_status"] = "granted"

    with pytest.raises(ValueError, match="unknown"):
        prepare_record(record)


def test_fingerprint_ignores_case_and_extra_whitespace():
    first = content_fingerprint(
        5,
        "All reports must be submitted by Friday.",
        {
            "A": "at",
            "B": "by",
            "C": "in",
            "D": "onward",
        },
    )

    second = content_fingerprint(
        5,
        "  ALL reports   must be submitted by Friday. ",
        {
            "A": " AT ",
            "B": "BY",
            "C": "in",
            "D": "onward",
        },
    )

    assert first == second


def test_fingerprint_changes_when_option_changes():
    first = content_fingerprint(
        5,
        "Reports are due _____ Friday.",
        {
            "A": "at",
            "B": "by",
            "C": "in",
            "D": "onward",
        },
    )

    second = content_fingerprint(
        5,
        "Reports are due _____ Friday.",
        {
            "A": "at",
            "B": "before",
            "C": "in",
            "D": "onward",
        },
    )

    assert first != second


def test_rejects_difficulty_outside_supported_range():
    record = sample_record()
    record["difficulty"] = 400

    with pytest.raises(ValueError, match="difficulty"):
        prepare_record(record)
