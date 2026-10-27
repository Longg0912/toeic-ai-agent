
from scripts.data_pipeline.audit_toeic_ocean_skills import (
    build_tag_inventory,
    normalize_options,
    normalize_tags,
)


def test_normalize_tags_removes_duplicates_and_whitespace():
    result = normalize_tags(
        [" Preposition ", "preposition", "WORD-FORM", "", None]
    )

    assert result == ["preposition", "word-form"]


def test_tag_inventory_maps_explicit_tag():
    records = [
        {
            "source_record_id": "P5-001",
            "text": "The report is due by Friday.",
            "source_tags": ["preposition"],
        }
    ]

    inventory = build_tag_inventory(
        records,
        {"preposition": "GRAMMAR_PREPOSITIONS"},
        {"GRAMMAR_PREPOSITIONS"},
    )

    assert inventory[0]["tag"] == "preposition"
    assert inventory[0]["occurrences"] == 1
    assert inventory[0]["classification"] == "mapped_to_skill"
    assert inventory[0]["mapped_skill_code"] == "GRAMMAR_PREPOSITIONS"


def test_generic_tags_are_marked_for_review():
    records = [
        {
            "source_record_id": "P5-001",
            "text": "Example question.",
            "source_tags": ["grammar", "reading", "vocabulary"],
        }
    ]

    inventory = build_tag_inventory(records, {}, set())
    by_tag = {item["tag"]: item for item in inventory}

    assert by_tag["grammar"]["classification"] == "generic_needs_review"
    assert by_tag["reading"]["classification"] == "generic_needs_review"
    assert by_tag["vocabulary"]["classification"] == "generic_needs_review"


def test_unmapped_tag_has_examples_for_review():
    records = [
        {
            "source_record_id": "P5-010",
            "text": "Employees must submit the form.",
            "source_tags": ["relative-clause"],
        }
    ]

    inventory = build_tag_inventory(records, {}, set())

    assert inventory[0]["classification"] == "needs_review"
    assert inventory[0]["examples"][0]["source_record_id"] == "P5-010"
    assert "Employees must submit" in inventory[0]["examples"][0]["text"]


def test_normalize_options_from_dictionary():
    result = normalize_options(
        {
            "B": "at",
            "A": "by",
            "D": "on",
            "C": "for",
        }
    )

    assert result == [
        {"key": "A", "text": "by"},
        {"key": "B", "text": "at"},
        {"key": "C", "text": "for"},
        {"key": "D", "text": "on"},
    ]


def test_normalize_options_from_list_of_objects():
    result = normalize_options(
        [
            {"option_key": "A", "content": "by"},
            {"option_key": "B", "content": "at"},
        ]
    )

    assert result == [
        {"key": "A", "text": "by"},
        {"key": "B", "text": "at"},
    ]
