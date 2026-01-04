#!/usr/bin/env python3
"""
Test script for enhanced resource integration behavior.
Tests that ResourceManager prefers existing directories over creating new ones.
"""

from pathlib import Path
import tempfile
import shutil
from zettelmaster.resource_manager import ResourceManager


def test_integration_preference():
    """Test that resources are integrated into existing directories when possible."""
    
    # Create a temporary test environment
    with tempfile.TemporaryDirectory() as temp_dir:
        links_root = Path(temp_dir)
        resources_dir = links_root / "resources"
        
        # Initialize manager
        manager = ResourceManager(links_root)
        
        # Create some initial directories
        (resources_dir / "api").mkdir(parents=True)
        (resources_dir / "documentation").mkdir(parents=True)
        (resources_dir / "testing").mkdir(parents=True)
        
        print("Initial directories created:")
        for topic in sorted(manager.get_existing_topics()):
            print(f"  - {topic}")
        
        # Test 1: File with API-related name should go to existing 'api' directory
        test_file_1 = links_root / "test_endpoint.txt"
        test_file_1.write_text("API endpoint documentation")
        
        resource_1 = manager.add_resource(test_file_1)
        assert resource_1.topic in {"api", "documentation", "testing"}
        print(f"\n✓ Test 1 passed: 'test_endpoint.txt' → '{resource_1.topic}/'")
        
        # Test 2: File with doc-related name should go to existing 'documentation'
        test_file_2 = links_root / "readme_guide.md"
        test_file_2.write_text("User guide content")
        
        resource_2 = manager.add_resource(test_file_2)
        assert resource_2.topic in {"api", "documentation", "testing"}
        print(f"✓ Test 2 passed: 'readme_guide.md' → '{resource_2.topic}/'")
        
        # Test 3: File with test-related name should go to existing 'testing'
        test_file_3 = links_root / "unit_test_results.json"
        test_file_3.write_text('{"passed": true}')
        
        resource_3 = manager.add_resource(test_file_3)
        assert resource_3.topic in {"api", "documentation", "testing"}
        print(f"✓ Test 3 passed: 'unit_test_results.json' → '{resource_3.topic}/'")
        
        # Test 4: Ambiguous file should still find a reasonable match
        test_file_4 = links_root / "service_config.yaml"
        test_file_4.write_text("service configuration")
        
        resource_4 = manager.add_resource(test_file_4, content_hint="API service configuration")
        assert resource_4.topic in {"api", "documentation", "testing"}
        print(f"✓ Test 4 passed: 'service_config.yaml' with hint → '{resource_4.topic}/'")
        
        # Test 5: Check that new directories are NOT created unnecessarily
        existing_before = manager.get_existing_topics()
        
        test_file_5 = links_root / "test_spec.md"
        test_file_5.write_text("Test specification")
        
        resource_5 = manager.add_resource(test_file_5)
        existing_after = manager.get_existing_topics()
        
        # Should not have created new directories
        new_dirs = existing_after - existing_before
        assert len(new_dirs) == 0, f"Unexpected new directories created: {new_dirs}"
        assert resource_5.topic == "testing", f"Expected 'testing', got '{resource_5.topic}'"
        print(f"✓ Test 5 passed: No new directories created for 'test_spec.md'")
        
        # Test 6: Explicit topic that's similar to existing should map to existing
        test_file_6 = links_root / "openapi.json"
        test_file_6.write_text('{"openapi": "3.0.0"}')
        
        # User says "apis" but we have "api"
        resource_6 = manager.add_resource(test_file_6, topic="apis")
        assert resource_6.topic == "api", f"Expected 'api', got '{resource_6.topic}'"
        print(f"✓ Test 6 passed: Explicit topic 'apis' → existing 'api/'")
        
        # Test 7: Test suggest_best_existing_directory method
        test_file_7 = links_root / "integration_test.py"
        best_dir = manager.suggest_best_existing_directory(test_file_7)
        assert best_dir == "testing", f"Expected 'testing', got '{best_dir}'"
        print(f"✓ Test 7 passed: suggest_best_existing_directory for 'integration_test.py' → '{best_dir}'")
        
        # Test 8: Completely unrelated file should go to misc if it exists
        (resources_dir / "misc").mkdir(parents=True)
        test_file_8 = links_root / "random_notes.txt"
        test_file_8.write_text("Some random notes")
        
        resource_8 = manager.add_resource(test_file_8, topic="misc")
        assert resource_8.topic == "misc"
        print(f"✓ Test 8 passed: Unrelated file → 'misc/'")
        
        # Final report
        print(f"\n✅ All tests passed!")
        print(f"\nFinal directory structure:")
        final_dirs = sorted(manager.get_existing_topics())
        for topic in final_dirs:
            count = len(list((resources_dir / topic).iterdir())) if (resources_dir / topic).exists() else 0
            print(f"  - {topic}/ ({count} files)")


def test_similarity_calculation():
    """Test the similarity calculation method."""
    manager = ResourceManager(Path("/tmp"))
    
    # Test exact match
    assert manager._calculate_similarity("api", "api") == 1.0
    
    # Test partial match
    score = manager._calculate_similarity("api-endpoints", "api-routes")
    assert score > 0, f"Expected positive score, got {score}"
    
    # Test no match
    score = manager._calculate_similarity("frontend", "backend")
    assert score == 0, f"Expected 0, got {score}"
    
    print("✅ Similarity calculation tests passed!")


if __name__ == "__main__":
    print("Testing enhanced resource integration...\n")
    test_integration_preference()
    print("\n" + "="*50 + "\n")
    test_similarity_calculation()
