#!/usr/bin/env python3
"""
Comprehensive tests for mandatory field validation and handling.
Tests all 8 mandatory fields with edge cases and error scenarios.
"""

import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict

from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.zettel_generator import ZettelGenerator, ZettelContent
from zettelmaster.zettel_parser import ZettelParser
from zettelmaster.config import (
    format_title_for_yaml,
    needs_title_quotes,
    is_title_descriptive,
    validate_date_format,
    get_mandatory_field_defaults
)


DEFAULT_TZ_OFFSET = 0.0


def make_generator() -> ZettelGenerator:
    return ZettelGenerator(timezone_offset=DEFAULT_TZ_OFFSET)


class TestMandatoryFields:
    """Test all mandatory field requirements"""

    def setup_method(self):
        """Setup for each test"""
        self.validator = ZettelValidator()
        self.generator = make_generator()

    def test_all_mandatory_fields_present(self):
        """Test that all 8 mandatory fields are required"""
        content = """---
id: 20250120153846
title: Test Zettel
date: 2025-01-20T15:38:46+01:00
tags:
  - test
  - validation
  - mandatory
type: note
publish: false
processed: false
synthetic: true
---

# Test Zettel

Content here."""

        result = self.validator.validate_zettel(content, "20250120153846.md")
        assert result.is_valid, f"Valid zettel rejected: {result.errors}"

    def test_missing_mandatory_fields(self):
        """Test detection of missing mandatory fields"""
        # Test each missing field
        mandatory_fields = [
            'id', 'title', 'date', 'tags', 
            'type', 'publish', 'processed', 'synthetic'
        ]
        
        for field in mandatory_fields:
            content = f"""---
{"id: 20250120153846" if field != 'id' else ""}
{"title: Test" if field != 'title' else ""}
{"date: 2025-01-20T15:38:46+01:00" if field != 'date' else ""}
{"tags:" if field != 'tags' else ""}
{"  - test" if field != 'tags' else ""}
{"  - valid" if field != 'tags' else ""}
{"  - check" if field != 'tags' else ""}
{"type: note" if field != 'type' else ""}
{"publish: false" if field != 'publish' else ""}
{"processed: false" if field != 'processed' else ""}
{"synthetic: true" if field != 'synthetic' else ""}
---

# Content

Body text."""

            result = self.validator.validate_zettel(content, "test.md")
            assert not result.is_valid, f"Missing {field} not detected"
            assert any(field in error for error in result.errors), \
                f"Missing {field} not in errors: {result.errors}"


class TestIdField:
    """Test ID field validation"""

    def setup_method(self):
        self.validator = ZettelValidator()
        self.generator = make_generator()

    def test_valid_id_format(self):
        """Test valid 14-digit ID format"""
        valid_ids = [
            "20250120153846",
            "19991231235959",
            "20000101000000",
        ]
        
        for id_val in valid_ids:
            content = f"""---
id: {id_val}
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
            result = self.validator.validate_zettel(content, f"{id_val}.md")
            assert result.is_valid, f"Valid ID {id_val} rejected: {result.errors}"

    def test_invalid_id_format(self):
        """Test invalid ID formats"""
        invalid_ids = [
            "2025012015384",    # 13 digits
            "202501201538467",  # 15 digits
            "2025-01-20",       # Wrong format
            "abcd1234567890",   # Contains letters
            "20250120 153846",  # Contains space
        ]
        
        for id_val in invalid_ids:
            content = f"""---
id: {id_val}
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
            result = self.validator.validate_zettel(content, "test.md")
            assert not result.is_valid, f"Invalid ID {id_val} not rejected"

    def test_id_generation(self):
        """Test automatic ID generation"""
        zettel_id = self.generator.generate_id()
        assert len(zettel_id) == 14
        assert zettel_id.isdigit()

        # Test uniqueness (wait at least one second to ensure new timestamp)
        import time
        time.sleep(1)
        id2 = self.generator.generate_id()
        assert zettel_id != id2  # Should be different once time advances


class TestTitleField:
    """Test title field validation and formatting"""

    def test_title_with_colon_needs_quotes(self):
        """Test titles containing colons require quotes"""
        assert needs_title_quotes("Docker: Container Management")
        assert needs_title_quotes("Understanding AI: A Deep Dive")
        assert not needs_title_quotes("Docker Container Management")
        assert not needs_title_quotes('"Docker: Already Quoted"')

    def test_format_title_for_yaml(self):
        """Test proper title formatting for YAML"""
        # Title with colon gets quoted
        assert format_title_for_yaml("Docker: Basics") == '"Docker: Basics"'
        
        # Title without colon stays unquoted
        assert format_title_for_yaml("Docker Basics") == "Docker Basics"
        
        # Already quoted title stays as is
        assert format_title_for_yaml('"Docker: Basics"') == '"Docker: Basics"'
        
        # Title with quotes inside gets escaped
        assert format_title_for_yaml('The "Best" Practices: A Guide') == \
               '"The \\"Best\\" Practices: A Guide"'

    def test_title_descriptiveness(self):
        """Test title descriptiveness validation"""
        # Descriptive titles
        assert is_title_descriptive("Understanding Neural Network Backpropagation")
        assert is_title_descriptive("Docker Container Orchestration with Kubernetes")
        
        # Vague titles
        assert not is_title_descriptive("Notes")
        assert not is_title_descriptive("Thoughts on stuff")
        assert not is_title_descriptive("Random ideas")
        assert not is_title_descriptive("Misc things")
        assert not is_title_descriptive("General overview")
        
        # Too short (less than 3 words)
        assert not is_title_descriptive("Docker")
        assert not is_title_descriptive("AI Basics")

    def test_title_length_validation(self):
        """Test title length constraints"""
        validator = ZettelValidator()
        
        # Too short
        short_title = "AI"
        content = f"""---
id: 20250120153846
title: {short_title}
date: 2025-01-20T15:38:46+01:00
tags: [ai, ml, test]
type: note
publish: false
processed: false
synthetic: true
---

# {short_title}"""
        result = validator.validate_zettel(content, "test.md")
        assert not result.is_valid
        assert any("too short" in e.lower() for e in result.errors)
        
        # Too long
        long_title = "A" * 201  # Over 200 char limit
        content = f"""---
id: 20250120153847
title: {long_title}
date: 2025-01-20T15:38:46+01:00
tags: [test, long, title]
type: note
publish: false
processed: false
synthetic: true
---

# Title"""
        result = validator.validate_zettel(content, "test.md")
        assert not result.is_valid
        assert any("too long" in e.lower() for e in result.errors)


class TestDateField:
    """Test date field validation"""

    def test_valid_date_formats(self):
        """Test valid ISO 8601 date formats with timezone"""
        valid_dates = [
            "2025-01-20T15:38:46+01:00",  # UTC+1
            "2025-01-20T06:38:46-08:00",  # UTC-8
            "2025-01-20T14:38:46+00:00",  # UTC
            "2025-12-31T23:59:59+12:00",  # UTC+12
            "2025-01-01T00:00:00-11:00",  # UTC-11
        ]
        
        for date in valid_dates:
            assert validate_date_format(date), f"Valid date {date} rejected"

    def test_invalid_date_formats(self):
        """Test invalid date formats"""
        invalid_dates = [
            "2025-01-20T15:38:46",         # Missing timezone
            "2025-01-20 15:38:46+01:00",   # Space instead of T
            "25-01-20T15:38:46+01:00",     # Wrong year format
            "2025/01/20T15:38:46+01:00",   # Wrong separator
            "2025-01-20T25:38:46+01:00",   # Invalid hour
            "2025-01-20T15:38:46+1:00",    # Wrong timezone format
            "January 20, 2025",             # Wrong format entirely
        ]
        
        for date in invalid_dates:
            assert not validate_date_format(date), f"Invalid date {date} not rejected"

    def test_date_generation(self):
        """Test automatic date generation"""
        generator = make_generator()
        date = generator.generate_date()
        
        # Check format
        assert validate_date_format(date)
        
        # Parse to verify it's a valid datetime
        # Format: YYYY-MM-DDTHH:MM:SS+HH:MM
        parts = date.replace('+', ' +').replace('-', ' -').rsplit(' ', 1)
        dt_part = parts[0]
        tz_part = parts[1] if len(parts) > 1 else "+00:00"
        
        # Verify datetime part is parseable
        datetime.strptime(dt_part.replace(' ', ''), "%Y-%m-%dT%H:%M:%S")


class TestTagsField:
    """Test tags field validation"""

    def setup_method(self):
        self.validator = ZettelValidator()

    def test_valid_tags(self):
        """Test valid tag formats"""
        valid_tag_sets = [
            ["ai", "machine-learning", "neural-networks"],
            ["python/data-structure", "algorithms", "optimization"],
            ["web-dev", "javascript/react", "frontend"],
            ["db", "sql", "postgresql", "indexing", "performance"],
        ]
        
        for tags in valid_tag_sets:
            content = f"""---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: {tags}
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
            result = self.validator.validate_zettel(content, "test.md")
            assert result.is_valid, f"Valid tags {tags} rejected: {result.errors}"

    def test_invalid_tag_formats(self):
        """Test invalid tag formats"""
        invalid_tags = [
            "Machine Learning",  # Capitals and space
            "machine_learning",  # Underscore
            "machine.learning",  # Dot
            "AI/NLP",           # Capitals
            "web dev",          # Space
            "c++",              # Special chars
        ]
        
        for tag in invalid_tags:
            content = f"""---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [{tag}, valid, test]
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
            result = self.validator.validate_zettel(content, "test.md")
            assert not result.is_valid, f"Invalid tag {tag} not rejected"

    def test_tag_count_validation(self):
        """Test tag count constraints (3-5)"""
        # Too few tags
        content_few = """---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [only, two]
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
        result = self.validator.validate_zettel(content_few, "test.md")
        assert not result.is_valid
        assert any("few tags" in e.lower() for e in result.errors)
        
        # Too many tags
        content_many = """---
id: 20250120153847
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [one, two, three, four, five, six]
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
        result = self.validator.validate_zettel(content_many, "test.md")
        assert not result.is_valid
        assert any("many tags" in e.lower() for e in result.errors)


class TestTypeField:
    """Test type field validation"""

    def setup_method(self):
        self.validator = ZettelValidator()
        self.generator = make_generator()

    def test_valid_types(self):
        """Test all valid type values"""
        valid_types = ['note', 'hub', 'toc', 'definition', 'snippet']
        
        for type_val in valid_types:
            content = f"""---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: {type_val}
publish: false
processed: false
synthetic: true
---

# Test"""
            filename = "test.md"
            if type_val == 'hub':
                filename = "test.hub.md"
            elif type_val == 'toc':
                filename = "test.toc.md"
            result = self.validator.validate_zettel(content, filename)
            assert result.is_valid, f"Valid type {type_val} rejected: {result.errors}"

    def test_invalid_types(self):
        """Test invalid type values"""
        invalid_types = ['article', 'post', 'page', 'custom', 'Note', 'SNIPPET']
        
        for type_val in invalid_types:
            content = f"""---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: {type_val}
publish: false
processed: false
synthetic: true
---

# Test"""
            result = self.validator.validate_zettel(content, "test.md")
            assert not result.is_valid, f"Invalid type {type_val} not rejected"

    def test_type_auto_detection(self):
        """Test automatic type detection"""
        # Definition detection
        def_title = "What is Machine Learning?"
        def_body = "Machine Learning is defined as..."
        detected = self.generator.detect_zettel_type(def_title, def_body, None)
        assert detected == 'definition'
        
        # Snippet detection
        snippet_body = """```python
def hello():
    print("Hello World")
```

This is a simple function."""
        detected = self.generator.detect_zettel_type("Hello Function", snippet_body, None)
        assert detected == 'snippet'
        
        # Hub detection
        hub_title = "Python Resources Hub"
        hub_body = """Overview of Python learning resources:

- [[python/basics]]
- [[python/advanced]]
- [[python/frameworks]]
- [[python/testing]]
- [[python/deployment]]
- [[python/best-practices]]"""
        detected = self.generator.detect_zettel_type(hub_title, hub_body, None)
        assert detected == 'hub'


class TestBooleanFields:
    """Test boolean mandatory fields"""

    def setup_method(self):
        self.validator = ZettelValidator()

    def test_valid_boolean_values(self):
        """Test valid boolean values"""
        content = """---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: false
processed: false
synthetic: true
---

# Test"""
        result = self.validator.validate_zettel(content, "test.md")
        assert result.is_valid

    def test_invalid_boolean_types(self):
        """Test invalid boolean types"""
        # String instead of boolean
        content = """---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: "false"
processed: false
synthetic: true
---

# Test"""
        result = self.validator.validate_zettel(content, "test.md")
        assert not result.is_valid
        assert any("boolean" in e.lower() for e in result.errors)

    def test_skill_constraints(self):
        """Test skill-specific constraints on boolean fields"""
        # publish must be false
        content_pub = """---
id: 20250120153846
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: true
processed: false
synthetic: true
---

# Test"""
        result = self.validator.validate_zettel(content_pub, "test.md")
        assert not result.is_valid
        assert any("publish" in e and "must be false" in e for e in result.errors)
        
        # processed must be false
        content_proc = """---
id: 20250120153847
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: false
processed: true
synthetic: true
---

# Test"""
        result = self.validator.validate_zettel(content_proc, "test.md")
        assert not result.is_valid
        assert any("processed" in e and "must be false" in e for e in result.errors)
        
        # synthetic must be true
        content_synth = """---
id: 20250120153848
title: Test
date: 2025-01-20T15:38:46+01:00
tags: [test, valid, check]
type: note
publish: false
processed: false
synthetic: false
---

# Test"""
        result = self.validator.validate_zettel(content_synth, "test.md")
        assert not result.is_valid
        assert any("synthetic" in e and "must be true" in e for e in result.errors)

    def test_default_values(self):
        """Test default values for mandatory boolean fields"""
        defaults = get_mandatory_field_defaults()
        assert defaults['publish'] == False
        assert defaults['processed'] == False
        assert defaults['synthetic'] == True


class TestIntegration:
    """Integration tests for mandatory fields"""

    def setup_method(self): 
        self.generator = make_generator()
        self.validator = ZettelValidator()
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        temp_path = Path(self._tmp.name)
        synthetic = temp_path / "synthetic"
        processed = temp_path / "processed"
        synthetic.mkdir()
        processed.mkdir()
        self.parser = ZettelParser(synthetic, processed)

    def teardown_method(self):
        self._tmp.cleanup()

    def test_full_generation_validation_cycle(self):
        """Test complete cycle: generate -> validate -> parse"""
        # Generate a zettel
        content = ZettelContent(
            title="Docker Compose: Multi-Container Applications",
            body="Docker Compose allows you to define multi-container applications...",
            tags=["docker", "containers", "devops"],
            type="note",
            publish=False,
            processed=False,
            synthetic=True
        )
        
        # Generate zettel text
        zettel_text = self.generator.generate_zettel(content)
        
        # Extract ID from generated text
        lines = zettel_text.split('\n')
        id_line = [l for l in lines if l.startswith('id:')][0]
        zettel_id = id_line.split(': ')[1]
        
        # Validate generated zettel
        result = self.validator.validate_zettel(zettel_text, f"{zettel_id}.md")
        assert result.is_valid, f"Generated zettel invalid: {result.errors}"
        
        # Parse the zettel
        parsed = self.parser.parse_content(zettel_text)
        assert parsed is not None
        
        # Verify all mandatory fields present and correct
        assert parsed.id == zettel_id
        assert parsed.title == "Docker Compose: Multi-Container Applications"
        assert len(parsed.tags) == 3
        assert parsed.type == "note"
        assert parsed.publish == False
        assert parsed.processed == False
        assert parsed.synthetic == True

    def test_edge_cases(self):
        """Test edge cases and boundary conditions"""
        # Maximum valid title length (200 chars)
        long_title = "A" * 200
        content = f"""---
id: 20250120153846
title: {long_title}
date: 2025-01-20T15:38:46+01:00
tags: [test, edge, case]
type: note
publish: false
processed: false
synthetic: true
---

# {long_title}"""
        result = self.validator.validate_zettel(content, "test.md")
        assert result.is_valid  # Exactly at limit should be valid
        
        # Exactly 3 tags (minimum)
        content_3tags = """---
id: 20250120153847
title: Testing Minimum Tags
date: 2025-01-20T15:38:46+01:00
tags: [one, two, three]
type: note
publish: false
processed: false
synthetic: true
---

# Testing Minimum Tags"""
        result = self.validator.validate_zettel(content_3tags, "test.md")
        assert result.is_valid
        
        # Exactly 5 tags (maximum)
        content_5tags = """---
id: 20250120153848
title: Testing Maximum Tags
date: 2025-01-20T15:38:46+01:00
tags: [one, two, three, four, five]
type: note
publish: false
processed: false
synthetic: true
---

# Testing Maximum Tags"""
        result = self.validator.validate_zettel(content_5tags, "test.md")
        assert result.is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
