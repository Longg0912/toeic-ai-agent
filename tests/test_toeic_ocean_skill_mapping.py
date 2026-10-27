import json

from scripts.data_pipeline.map_toeic_ocean_skills import (
    build_mapping_plan,
    load_manifest,
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
    "business-verb": "VOCAB_BUSINESS",
    "vocabulary": "VOCAB_BUSINESS",
}


CATEGORY_TO_SKILL = {
    "詞性": "GRAMMAR_WORD_FORM",
    "時態": "GRAMMAR_TENSES",
}


def make_record(
    record_id: str,
    tags: list[str],
    source_category: str | None = None,
) -> dict:
    return {
        "source_record_id": record_id,
        "source_url": "https://example.com/repository",
        "source_tags": tags,
        "source_category": source_category,
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


def test_maps_business_vocabulary_to_business_skill():
    plan, _, counts = build_mapping_plan(
        [
            make_record(
                "P5-005",
                ["business-verb", "vocabulary"],
            )
        ],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["VOCAB_BUSINESS"]
    assert counts["VOCAB_BUSINESS"] == 1


def test_case_and_whitespace_are_normalized_for_tags():
    plan, _, _ = build_mapping_plan(
        [make_record("P5-006", [" Word-Form "])],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]


def test_unmapped_question_is_not_assigned_any_skill():
    plan, _, _ = build_mapping_plan(
        [
            make_record(
                "P5-007",
                ["relative-clause", "passive"],
            )
        ],
        TAG_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == []


def test_maps_source_category_when_tag_is_generic():
    plan, unmapped, counts = build_mapping_plan(
        [
            make_record(
                "P5-008",
                ["grammar"],
                "詞性",
            )
        ],
        TAG_TO_SKILL,
        CATEGORY_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]
    assert plan[0]["mapped_source_category"] == "詞性"
    assert plan[0]["unmapped_source_category"] is None
    assert unmapped["grammar"] == 1
    assert counts["GRAMMAR_WORD_FORM"] == 1


def test_tag_and_category_mapping_to_same_skill_are_deduplicated():
    plan, _, counts = build_mapping_plan(
        [
            make_record(
                "P5-009",
                ["word-form"],
                "詞性",
            )
        ],
        TAG_TO_SKILL,
        CATEGORY_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]
    assert counts["GRAMMAR_WORD_FORM"] == 1


def test_tag_and_category_can_map_to_different_skills():
    plan, _, counts = build_mapping_plan(
        [
            make_record(
                "P5-010",
                ["business-verb"],
                "詞性",
            )
        ],
        TAG_TO_SKILL,
        CATEGORY_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == [
        "GRAMMAR_WORD_FORM",
        "VOCAB_BUSINESS",
    ]
    assert counts["GRAMMAR_WORD_FORM"] == 1
    assert counts["VOCAB_BUSINESS"] == 1


def test_unmapped_source_category_is_preserved_for_review():
    plan, _, _ = build_mapping_plan(
        [
            make_record(
                "P5-011",
                ["grammar"],
                "固定搭配",
            )
        ],
        TAG_TO_SKILL,
        CATEGORY_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == []
    assert plan[0]["mapped_source_category"] is None
    assert plan[0]["unmapped_source_category"] == "固定搭配"


def test_source_category_whitespace_is_normalized():
    plan, _, _ = build_mapping_plan(
        [
            make_record(
                "P5-012",
                ["grammar"],
                " 詞性 ",
            )
        ],
        TAG_TO_SKILL,
        CATEGORY_TO_SKILL,
    )

    assert plan[0]["skill_codes"] == ["GRAMMAR_WORD_FORM"]
    assert plan[0]["mapped_source_category"] == "詞性"


def test_load_manifest_reads_both_mapping_tables(tmp_path):
    manifest_path = tmp_path / "manifest.json"

    manifest = {
        "schema_version": "1.0",
        "tag_to_skill": {
            " Word-Form ": " GRAMMAR_WORD_FORM ",
        },
        "category_to_skill": {
            " 詞性 ": " GRAMMAR_WORD_FORM ",
        },
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    tag_mapping, category_mapping = load_manifest(manifest_path)

    assert tag_mapping == {
        "word-form": "GRAMMAR_WORD_FORM",
    }

    assert category_mapping == {
        "詞性": "GRAMMAR_WORD_FORM",
    }