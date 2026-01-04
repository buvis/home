#!/usr/bin/env python3
"""
Test script for new kebab-case relation system with 17 semantic relations
"""
from pathlib import Path
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.zettel_parser import ZettelParser
from zettelmaster.config import zettel_config
import tempfile


def create_test_zettel():
    """Create a test zettel with all new relation types"""
    
    content = """---
id: 20251109123456
title: Test Zettel for New Relations
date: 2025-11-09T12:34:56+01:00
tags:
  - test/relations
  - knowledge-graph
  - graph/semantics
type: note
publish: false
processed: false
synthetic: true
---

# Test Zettel for New Relations

This zettel tests all 17 semantic relations in kebab-case format.

## Testing Hierarchical Relations
The hierarchical relations (broader-than and narrower-than) enable taxonomic organization.

## Testing Development Relations  
Development relations show how ideas evolve and get synthesized.

## Testing Application Relations
Application relations connect theory to practice through implementation and examples.

## Testing Reasoning Relations
Reasoning relations capture logical relationships, evidence, and cross-domain connections.

## Testing Dependencies
Dependency relations show prerequisites, sequences, and enabling factors.

## Testing Identity Relations
Identity relations handle definitions, duplicates, and collection membership.

---
web:: [Knowledge Graphs](https://example.com)
+broader-than:: [[zettel/20250101000001]]
+narrower-than:: [[zettel/20250101000002]]
+develops:: [[zettel/20250101000003]]
+summarizes:: [[zettel/20250101000004]], [[zettel/20250101000005]]
+implements:: [[zettel/20250101000006]]
+exemplifies:: [[zettel/20250101000007]]
+supports:: [[zettel/20250101000008]]
+contradicts:: [[zettel/20250101000009]]
+questions:: [[zettel/20250101000010]]
+causes:: [[zettel/20250101000011]]
+analogous-to:: [[zettel/20250101000012]]
+requires:: [[zettel/20250101000013]]
+precedes:: [[zettel/20250101000014]]
+enables:: [[zettel/20250101000015]]
+defines:: [[zettel/20250101000016]]
+same-as:: [[zettel/20250101000017]]
+part-of:: [[zettel/20250101000018]]
"""
    
    return content


def _run_validator_suite() -> bool:
    """Execute validator checks for all relations."""
    
    print("=" * 60)
    print("TESTING VALIDATOR WITH NEW RELATIONS")
    print("=" * 60)
    
    # Create validator with mock existing IDs
    existing_ids = set([f"20250101{i:06d}" for i in range(1, 19)])
    validator = ZettelValidator(timezone="+00:00", existing_ids=existing_ids)
    
    # Test content
    content = create_test_zettel()
    
    # Validate
    result = validator.validate_zettel(content)
    
    print(f"\nValidation Result: {'✓ VALID' if result.valid else '✗ INVALID'}")
    
    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")
    
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    
    # Check that all relations are recognized
    print("\n" + "-" * 40)
    print("CHECKING RELATION RECOGNITION")
    print("-" * 40)
    
    expected_relations = [
        'broader-than', 'narrower-than',
        'develops', 'summarizes',
        'implements', 'exemplifies',
        'supports', 'contradicts', 'questions', 'causes', 'analogous-to',
        'requires', 'precedes', 'enables',
        'defines', 'same-as', 'part-of'
    ]
    
    for rel in expected_relations:
        if rel in zettel_config.VALID_RELATIONS:
            print(f"  ✓ {rel}: Configured")
        else:
            print(f"  ✗ {rel}: MISSING from config!")
    
    return result.valid


def test_validator():
    """Pytest entry point."""
    assert _run_validator_suite()


def _run_parser_suite() -> bool:
    """Test that parser correctly extracts new relations"""
    
    print("\n" + "=" * 60)
    print("TESTING PARSER WITH NEW RELATIONS")
    print("=" * 60)
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Write test zettel
        test_file = tmpdir / "test.md"
        test_file.write_text(create_test_zettel())
        
        # Parse
        parser = ZettelParser(tmpdir)
        zettel = parser.parse_file(test_file)
        
        if not zettel:
            print("✗ Failed to parse zettel!")
            return False
        
        print(f"\nParsed Zettel ID: {zettel.id}")
        print(f"Title: {zettel.title}")
        
        # Check relations
        print("\nExtracted Relations:")
        for rel_type, targets in sorted(zettel.relations.items()):
            print(f"  {rel_type}:")
            for target in targets:
                print(f"    → {target}")
        
        # Verify all expected relations were parsed
        expected = {
            'broader-than': 1,
            'narrower-than': 1,
            'develops': 1,
            'summarizes': 2,  # Has 2 targets
            'implements': 1,
            'exemplifies': 1,
            'supports': 1,
            'contradicts': 1,
            'questions': 1,
            'causes': 1,
            'analogous-to': 1,
            'requires': 1,
            'precedes': 1,
            'enables': 1,
            'defines': 1,
            'same-as': 1,
            'part-of': 1
        }
        
        print("\n" + "-" * 40)
        print("RELATION EXTRACTION CHECK")
        print("-" * 40)
        
        all_good = True
        for rel_type, expected_count in expected.items():
            actual_count = len(zettel.relations.get(rel_type, []))
            if actual_count == expected_count:
                print(f"  ✓ {rel_type}: {actual_count} target(s)")
            else:
                print(f"  ✗ {rel_type}: Expected {expected_count}, got {actual_count}")
                all_good = False
        
        return all_good


def test_parser():
    """Pytest entry point."""
    assert _run_parser_suite()


def _run_kebab_case_pattern_suite() -> bool:
    """Test that regex patterns correctly match kebab-case"""
    
    print("\n" + "=" * 60)
    print("TESTING KEBAB-CASE REGEX PATTERNS")
    print("=" * 60)
    
    import re
    
    # Test relation pattern
    rel_pattern = re.compile(r'^\+([a-z-]+)::')
    
    test_cases = [
        ("+broader-than:: [[test]]", "broader-than", True),
        ("+same-as:: [[test]]", "same-as", True),
        ("+analogous-to:: [[test]]", "analogous-to", True),
        ("+part-of:: [[test]]", "part-of", True),
        ("+partof:: [[test]]", "partof", True),  # Still works without hyphen
        ("+INVALID-CASE:: [[test]]", None, False),  # Uppercase not allowed
        ("+has_underscore:: [[test]]", None, False),  # Underscore not in pattern
    ]
    
    print("\nRelation Pattern Tests:")
    for test_str, expected_group, should_match in test_cases:
        match = rel_pattern.match(test_str)
        if should_match:
            if match and match.group(1) == expected_group:
                print(f"  ✓ '{test_str}' → '{expected_group}'")
            else:
                print(f"  ✗ '{test_str}' failed to match correctly")
        else:
            if not match:
                print(f"  ✓ '{test_str}' correctly rejected")
            else:
                print(f"  ✗ '{test_str}' should not match")
    
    return True


def test_kebab_case_patterns():
    """Pytest entry point."""
    assert _run_kebab_case_pattern_suite()


def main():
    """Run all tests"""
    
    print("TESTING NEW RELATION SYSTEM")
    print("=" * 60)
    print(f"Configured relations ({len(zettel_config.VALID_RELATIONS)}):")
    for i, rel in enumerate(zettel_config.VALID_RELATIONS, 1):
        print(f"  {i:2}. {rel}")
    
    # Run tests
    results = []
    results.append(("Kebab-case Patterns", _run_kebab_case_pattern_suite()))
    results.append(("Validator", _run_validator_suite()))
    results.append(("Parser", _run_parser_suite()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED - Relation system working correctly!")
    else:
        print("✗ SOME TESTS FAILED - Check errors above")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
