# Hub and TOC Zettel Enhancement

## Overview
Enhanced the Zettelmaster skill to properly handle hub and TOC zettels with specific file naming conventions and abstraction requirements.

## Key Changes

### 1. File Naming Convention
- **Hub zettels**: Use `{slugified-title}.hub.md` format (e.g., `machine-learning.hub.md`)
- **TOC zettels**: Use `{slugified-title}.toc.md` format (e.g., `python-programming.toc.md`)
- **Regular zettels**: Continue using `{zettel_id}.md` format (e.g., `20251107143022.md`)

### 2. Slugify Function
Added `slugify()` method to `ZettelGenerator` class:
- Converts titles to kebab-case
- Removes special characters
- Converts spaces and underscores to hyphens
- Ensures lowercase output

### 3. Enhanced Hub Generation
- Ensures abstract, non-specific content
- Automatically includes 'hub' tag
- Removes words like "specific", "particular", "my" from content
- Follows standard zettel structure with all mandatory metadata
- Properly formats relations with wikilinks

### 4. Enhanced TOC Generation
- Ensures abstract, non-specific content
- Automatically includes 'toc' and 'index' tags
- Removes specific/personal terms from content
- Supports priority indicators for items
- Properly formats relations with wikilinks

### 5. Validation Enhancements
- Added filename validation for hub/TOC files
- Validates that hub/TOC titles are general/abstract
- Warns about specific words like "my", "personal", "particular"
- Ensures proper tags are included for each type

## Bug Fixes
- Fixed variable shadowing issue in `generate_toc()` where loop variable was overwriting method parameter
- Fixed relation formatting to always use wikilinks (`[[id]]` format)
- Fixed `ZettelGenerator` initialization in validator to provide required timezone_offset

## Files Modified
- `scripts/zettel_generator.py`: Added slugify(), updated save_zettel(), enhanced hub/TOC generation
- `scripts/zettel_validator.py`: Added hub/TOC validation, filename checks, abstraction warnings

## Testing
All enhancements have been tested with comprehensive test cases covering:
- Slugification of various title formats
- Hub generation with proper file naming
- TOC generation with proper file naming
- Abstraction validation warnings
- File saving with correct naming conventions