#!/usr/bin/env python3
"""
Test the enhanced type detection system for zettels.
"""

import sys

from zettelmaster.zettel_generator import ZettelGenerator, ZettelContent
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.config import zettel_config


def _run_type_detection_suite() -> bool:
    """Test automatic type detection for different zettel types."""

    generator = ZettelGenerator(timezone_offset=-8.0)  # PST timezone
    validator = ZettelValidator()

    print("=" * 60)
    print("TESTING ZETTEL TYPE DETECTION SYSTEM")
    print("=" * 60)

    # Test cases
    test_cases = [
        # Definition type detection
        {
            "title": "What is Machine Learning",
            "body": "Machine Learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.",
            "expected_type": "definition"
        },
        {
            "title": "Definition of Neural Networks",
            "body": "Neural networks are computing systems inspired by biological neural networks that constitute animal brains.",
            "expected_type": "definition"
        },
        {
            "title": "REST API",
            "body": "REST refers to Representational State Transfer, an architectural style for designing networked applications.",
            "expected_type": "definition"
        },
        
        # Snippet type detection
        {
            "title": "Python List Comprehension",
            "body": """```python
# List comprehension example
squares = [x**2 for x in range(10)]
print(squares)
```

List comprehensions provide a concise way to create lists.""",
            "expected_type": "snippet"
        },
        {
            "title": "Implementation of Binary Search",
            "body": """Implementation:

```python
def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```

Time complexity: O(log n)""",
            "expected_type": "snippet"
        },
        
        # Note type (default)
        {
            "title": "Benefits of Test-Driven Development",
            "body": "TDD helps ensure code quality by writing tests before implementation. It leads to better design decisions and provides a safety net for refactoring.",
            "expected_type": "note"
        },
        {
            "title": "Project Architecture Overview",
            "body": "The system follows a microservices architecture with separate services for authentication, data processing, and API gateway.",
            "expected_type": "note"
        },
        
        # Hub type (explicitly set)
        {
            "title": "Machine Learning Resources Hub",
            "body": """Hub for machine learning domain.

## Core Concepts
- [[zettel/20251101000001]] – Introduction to ML
- [[zettel/20251101000002]] – Supervised Learning

## Algorithms
- [[zettel/20251101000003]] – Linear Regression
- [[zettel/20251101000004]] – Decision Trees""",
            "explicit_type": "hub",
            "expected_type": "hub"
        },
        
        # TOC type (explicitly set)
        {
            "title": "Python Programming TOC",
            "body": """Ranked index for Python programming.

## Essential
1. [[zettel/20251101000001]] – Python Basics
2. [[zettel/20251101000002]] – Data Types

## Intermediate
1. [[zettel/20251101000003]] – Functions and Modules
2. [[zettel/20251101000004]] – Object-Oriented Programming""",
            "explicit_type": "toc",
            "expected_type": "toc"
        }
    ]
    
    # Test each case
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['title'][:40]}...")
        
        # Detect type
        detected_type = generator.detect_zettel_type(
            test_case["title"],
            test_case["body"],
            test_case.get("explicit_type")
        )
        
        # Check if detection is correct
        expected = test_case["expected_type"]
        if detected_type == expected:
            print(f"  ✓ PASSED: Correctly detected as '{detected_type}'")
            passed += 1
        else:
            print(f"  ✗ FAILED: Expected '{expected}', got '{detected_type}'")
            failed += 1
            
        # Generate zettel and validate
        content = ZettelContent(
            title=test_case["title"],
            body=test_case["body"],
            tags=["test", "type-detection"],
            type=test_case.get("explicit_type")  # Don't set default, let auto-detect work
        )

        zettel_markdown = generator.generate_zettel(content)
        
        # Parse the generated markdown to verify type
        lines = zettel_markdown.split('\n')
        type_line = [line for line in lines if line.startswith('type:')][0]
        generated_type = type_line.split(':')[1].strip()
        
        if generated_type == expected:
            print(f"  ✓ Generated zettel has correct type: '{generated_type}'")
        else:
            print(f"  ✗ Generated zettel has wrong type: '{generated_type}'")
        
        # Validate the zettel
        validation_result = validator.validate_zettel(zettel_markdown)
        if validation_result.valid:
            print(f"  ✓ Zettel passes validation")
        else:
            print(f"  ✗ Validation failed: {validation_result.errors}")
    
    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 60)
    
    # Test that all configured types are valid
    print(f"\nConfigured types: {zettel_config.VALID_TYPES}")
    print(f"Default type: {zettel_config.DEFAULT_TYPE}")
    
    return passed == len(test_cases)


def test_type_detection():
    """Pytest entry point."""
    assert _run_type_detection_suite()


def test_code_snippet_percentage_detection():
    """Test detection of snippets based on code percentage."""
    
    generator = ZettelGenerator(timezone_offset=-8.0)
    
    print("\n" + "=" * 60)
    print("TESTING CODE PERCENTAGE DETECTION")
    print("=" * 60)
    
    # High code percentage (should be snippet)
    high_code_content = """Here's how to implement a stack:

```python
class Stack:
    def __init__(self):
        self.items = []
```

Push operation:

```python
def push(self, item):
    self.items.append(item)
```

Pop operation:

```python
def pop(self):
    if not self.is_empty():
        return self.items.pop()
    return None
```

Check if empty:

```python
def is_empty(self):
    return len(self.items) == 0
```

This implementation uses a Python list as the underlying data structure."""
    
    detected = generator.detect_zettel_type("Stack Implementation", high_code_content)
    print(f"\nHigh code percentage content detected as: '{detected}'")
    print(f"Expected: 'snippet' - {'✓ PASSED' if detected == 'snippet' else '✗ FAILED'}")
    
    # Low code percentage (should be note)
    low_code_content = """Stacks are a fundamental data structure in computer science that follow the Last-In-First-Out (LIFO) principle.

The main operations are:
- Push: Add an element to the top
- Pop: Remove and return the top element
- Peek: View the top element without removing it
- isEmpty: Check if the stack is empty

Real-world applications include:
- Function call management in programming languages
- Expression evaluation and syntax parsing
- Undo mechanisms in text editors
- Browser back button functionality

Here's a simple example:

```python
stack = []
stack.append(1)  # Push
top = stack.pop()  # Pop
```

Stacks can be implemented using arrays or linked lists, each with different performance characteristics."""
    
    detected = generator.detect_zettel_type("Understanding Stacks", low_code_content)
    print(f"\nLow code percentage content detected as: '{detected}'")
    print(f"Expected: 'note' - {'✓ PASSED' if detected == 'note' else '✗ FAILED'}")


if __name__ == "__main__":
    # Run tests
    success = _run_type_detection_suite()
    test_code_snippet_percentage_detection()
    
    if success:
        print("\n✅ All type detection tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed.")
        sys.exit(1)
