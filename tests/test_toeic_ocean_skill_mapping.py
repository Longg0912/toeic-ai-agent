
from scripts.data_pipeline.map_toeic_ocean_skills import (
    build_mapping_plan,
)


TAG_TO_SKILL = {
    "word-form": "GRAMMAR_WORD_FORM",
    "present-perfect": "GRAMMAR_TENSES",
    "past-perfect": "GRAMMAR_TENSES",
    "subject-verb": "GRAMMAR_SUBJECT_VERB_AGREEMENT",
    "preposition": "GRAMMAR_PREPOSITIONS",
    "because-of": "GRAMMAR_PREPOSITIONS",
    "be-adj-prep": "GRAMMAR_PREPOSITIONS",
    "prep-relative": "GRAMMAR_PREPOSITIONS",
}


def make_record(record_id: str, tags: list[str]) -> dict:
    return {
        "source_record_id": record_id,
        "source_url": "https://example.com/repository",
        "source_tags": tags,
        "text": "Example TOEIC question",
    }


def test_maps_explicit_word_form_tag():
    plan, _, _ = build_mapping_plan(
        [make_record("P5-001", ["word-form"])],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]


def test_maps_tense_tags_to_same_skill_once():
    plan, _, counts = build_mapping_plan(
        [
            make_record(
                "P5-002",
                ["present-perfect", "past-perfect"],
            )
        ],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_TENSES"]
    assert counts["GRAMMAR_TENSES"] == 1


def test_maps_preposition_tags_without_duplicate_link():
    plan, _, counts = build_mapping_plan(
        [
            make_record(
                "P5-003",
                ["preposition", "be-adj-prep"],
            )
        ],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_PREPOSITIONS"]
    assert counts["GRAMMAR_PREPOSITIONS"] == 1


def test_preserves_unmapped_tags_for_review():
    plan, unmapped, _ = build_mapping_plan(
        [
            make_record(
                "P5-004",
                ["inversion", "grammar", "word-form"],
            )
        ],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]
    assert plan[0]["unmapped_tags"] == ["grammar", "inversion"]
    assert unmapped["inversion"] == 1


def test_does_not_guess_business_vocabulary():
    plan, _, _ = build_mapping_plan(
        [
            make_record(
                "P5-005",
                ["business-verb", "vocabulary"],
            )
        ],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == []


def test_case_and_whitespace_are_normalized():
    plan, _, _ = build_mapping_plan(
        [make_record("P5-006", [" Word-Form "])],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]


def test_unmapped_question_is_not_assigned_any_skill():
    plan, _, _ = build_mapping_plan(
        [make_record("P5-007", ["relative-clause", "passive"])],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == []
