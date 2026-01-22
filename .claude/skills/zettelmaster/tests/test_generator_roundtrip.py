from pathlib import Path

from zettelmaster.zettel_generator import ZettelGenerator, ZettelContent
from zettelmaster.zettel_parser import ZettelParser
from zettelmaster.zettel_validator import ZettelValidator


def test_generator_parser_validator_roundtrip(tmp_path):
    synthetic_dir = tmp_path / "synthetic"
    processed_dir = tmp_path / "processed"
    synthetic_dir.mkdir()
    processed_dir.mkdir()

    reference_target_id = "20240101010101"
    new_zettel_id = "20250101010101"

    generator = ZettelGenerator(timezone_offset=0)
    content = ZettelContent(
        title="Round-trip Validation: Example Concept",
        body="Atomic explanation that references and develops prior work.",
        tags=["ai/reasoning", "knowledge/base", "zettelmaster"],
        references={"source": "[Reference](https://example.com/resource)"},
        relations={"develops": [reference_target_id]},
    )

    markdown = generator.generate_zettel(
        content,
        zettel_id=new_zettel_id,
        date="2025-01-01T00:00:00+00:00",
    )

    zettel_path = synthetic_dir / f"{new_zettel_id}.md"
    zettel_path.write_text(markdown, encoding="utf-8")

    parser = ZettelParser(synthetic_dir, processed_dir)
    parsed = parser.parse_file(zettel_path)

    assert parsed is not None
    assert parsed.references["source"].startswith("[Reference]")
    assert "develops" in parsed.relations
    assert parsed.relations["develops"][0].endswith(reference_target_id)

    validator = ZettelValidator(existing_ids={reference_target_id, new_zettel_id})
    result = validator.validate_zettel(markdown, filepath=zettel_path)
    assert result.valid, f"Validation errors: {result.errors}"
