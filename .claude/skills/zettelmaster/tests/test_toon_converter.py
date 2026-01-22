import textwrap

import pytest

from zettelmaster.toon_converter import TOONConverter


def test_dict_round_trip_preserves_scalars():
    converter = TOONConverter()
    payload = {
        "name": "Test Zettel",
        "id": "20240203040506",
        "tags": ["ai/llm", "methodology"],
        "metadata": {"score": 42, "published": False},
    }

    toon = converter.dict_to_toon(payload)
    restored = converter.toon_to_dict(toon)

    assert restored == payload


def test_relations_are_grouped_under_relations_key():
    toon = textwrap.dedent(
        """
        id: 20240203040506
        title: Sample
        relations
          +broader-than:: [[zettel/123]]
          +supports:: [[zettel/456]]
        """
    ).strip()

    converter = TOONConverter()
    data = converter.toon_to_dict(toon)

    assert data["relations"] == {
        "broader-than": ["zettel/123"],
        "supports": ["zettel/456"],
    }


def test_proposals_round_trip_adds_missing_ids():
    converter = TOONConverter()
    proposals = [
        {
            "title": "Concept",
            "body": "Body",
            "tags": ["concepts/core"],
            "relations": {"supports": ["20240101010101"]},
        }
    ]

    toon = converter.proposals_to_toon(proposals)
    restored = converter.toon_to_proposals(toon)

    assert len(restored) == 1
    restored_entry = restored[0]
    assert restored_entry["title"] == "Concept"
    assert restored_entry["relations"] == {"supports": ["20240101010101"]}
    assert restored_entry["id"].startswith("zettel_")
