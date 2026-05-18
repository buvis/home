import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "survey" / "scripts"))

from run import _compute_naming_conventions


def _sym(name: str, layer: str = "api") -> dict:
    return {"file": "x.py", "kind": "function", "name": name, "layer": layer}


def test_empty_symbols_returns_empty_dict():
    assert _compute_naming_conventions([]) == {}


def test_classifies_snake_case():
    result = _compute_naming_conventions([_sym("my_func")])
    assert result["api"]["snake_case"] == 1
    assert result["api"]["dominant"] == "snake_case"


def test_classifies_camel_case():
    result = _compute_naming_conventions([_sym("MyClass")])
    assert result["api"]["CamelCase"] == 1
    assert result["api"]["dominant"] == "CamelCase"


def test_classifies_upper_snake():
    result = _compute_naming_conventions([_sym("MAX_VALUE")])
    assert result["api"]["UPPER_SNAKE"] == 1
    assert result["api"]["dominant"] == "UPPER_SNAKE"


def test_dominant_snake_case_wins_tie_over_camel():
    symbols = [_sym("my_func"), _sym("MyClass")]
    result = _compute_naming_conventions(symbols)
    assert result["api"]["snake_case"] == 1
    assert result["api"]["CamelCase"] == 1
    assert result["api"]["dominant"] == "snake_case"


def test_groups_by_layer():
    symbols = [_sym("my_func", "api"), _sym("MyClass", "cli")]
    result = _compute_naming_conventions(symbols)
    assert "api" in result
    assert "cli" in result
    assert result["api"]["snake_case"] == 1
    assert result["cli"]["CamelCase"] == 1
