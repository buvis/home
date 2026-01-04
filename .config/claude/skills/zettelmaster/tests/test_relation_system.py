#!/usr/bin/env python3
"""
Test script for the complete relation discovery system
"""
from pathlib import Path
from zettelmaster.relation_checker import RelationChecker, RelationGap, RelationAudit
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.config import RelationDiscoveryConfig


# Test Zettel class for demonstration
class TestZettel:
    def __init__(self, id, title, tags, references):
        self.id = id
        self.title = title
        self.tags = tags
        self.references = references
        self.body = ""
        self.relations = {}
        
        # Parse relations from references
        for rel_type, target in references:
            if rel_type not in self.relations:
                self.relations[rel_type] = []
            self.relations[rel_type].append(target)


def test_orphan_detection():
    """Test detection of orphan zettels (too few relations)"""
    print("=" * 60)
    print("TEST: ORPHAN DETECTION")
    print("=" * 60)
    
    # Create some existing zettels for context
    existing = {
        "TEST002": TestZettel("TEST002", "Related Concept", ["programming"], [])
    }
    checker = RelationChecker(existing)
    
    # Orphan zettel with only 1 relation
    orphan = TestZettel(
        id="TEST001",
        title="Isolated Concept",
        tags=["programming", "design"],
        references=[("related-to", "TEST002")]
    )
    
    audit = checker.audit_zettel(orphan)
    
    print(f"Zettel: {orphan.title} ({orphan.id})")
    print(f"  Relations: {audit.current_relation_count}")
    print(f"  Is Orphan: {audit.is_orphan}")
    print(f"  Missing Relations: {len(audit.missing_relations)}")
    
    if audit.warnings:
        print("  Warnings:")
        for warning in audit.warnings:
            print(f"    - {warning}")
    print()


def test_optimal_relations():
    """Test zettel with optimal number of relations"""
    print("=" * 60)
    print("TEST: OPTIMAL RELATIONS")
    print("=" * 60)
    
    # Create existing zettels
    existing = {
        "TEST001": TestZettel("TEST001", "Child Concept", ["patterns"], []),
        "TEST002": TestZettel("TEST002", "Related Pattern", ["patterns"], []),
        "TEST004": TestZettel("TEST004", "Parent Concept", ["architecture"], []),
        "TEST005": TestZettel("TEST005", "Example Implementation", ["implementation"], [])
    }
    checker = RelationChecker(existing)
    
    # Well-connected zettel
    optimal = TestZettel(
        id="TEST003",
        title="Core Architecture Pattern",
        tags=["architecture", "patterns", "design"],
        references=[
            ("broader-than", "TEST004"),
            ("narrower-than", "TEST001"),
            ("related-to", "TEST002"),
            ("exemplifies", "TEST005")
        ]
    )
    
    audit = checker.audit_zettel(optimal)
    
    print(f"Zettel: {optimal.title} ({optimal.id})")
    print(f"  Relations: {audit.current_relation_count}")
    print(f"  Is Orphan: {audit.is_orphan}")
    print(f"  Over-linked: {audit.over_linked}")
    print(f"  Status: {'✓ Optimal' if 3 <= audit.current_relation_count <= 5 else 'Could be improved'}")
    print()


def test_over_linked():
    """Test detection of over-linked zettels"""
    print("=" * 60)
    print("TEST: OVER-LINKED DETECTION")
    print("=" * 60)
    
    # Create many existing zettels
    existing = {f"TEST{i:03d}": TestZettel(f"TEST{i:03d}", f"Concept {i}", ["test"], []) 
                for i in range(10, 20)}
    checker = RelationChecker(existing)
    
    # Over-linked zettel
    overlinked = TestZettel(
        id="TEST006",
        title="Central Hub Concept",
        tags=["everything", "connected"],
        references=[
            ("related-to", f"TEST{i:03d}") for i in range(10, 20)
        ]
    )
    
    audit = checker.audit_zettel(overlinked)
    
    print(f"Zettel: {overlinked.title} ({overlinked.id})")
    print(f"  Relations: {audit.current_relation_count}")
    print(f"  Over-linked: {audit.over_linked}")
    
    if audit.warnings:
        print("  Warnings:")
        for warning in audit.warnings:
            print(f"    - {warning}")
    print()


def test_batch_audit():
    """Test batch auditing of multiple zettels"""
    print("=" * 60)
    print("TEST: BATCH AUDIT")
    print("=" * 60)
    
    # Empty existing for batch self-reference
    existing = {}
    checker = RelationChecker(existing)
    
    # Create a batch of related zettels
    batch = [
        TestZettel("BATCH001", "Microservices Architecture", 
                   ["architecture", "microservices"],
                   [("broader-than", "BATCH002")]),
        
        TestZettel("BATCH002", "Service Discovery", 
                   ["microservices", "networking"],
                   [("narrower-than", "BATCH001"), 
                    ("related-to", "BATCH003")]),
        
        TestZettel("BATCH003", "Load Balancing", 
                   ["networking", "performance"],
                   [("related-to", "BATCH002")]),
        
        TestZettel("BATCH004", "Circuit Breaker Pattern", 
                   ["patterns", "resilience"],
                   [])  # Orphan in the batch
    ]
    
    batch_results = checker.audit_batch(batch)
    
    print("Batch Analysis Results:")
    print(f"  Total Zettels: {len(batch)}")
    
    orphans = [zid for zid, audit in batch_results.items() if audit.is_orphan]
    overlinked = [zid for zid, audit in batch_results.items() if audit.over_linked]
    
    print(f"  Orphans: {len(orphans)} {orphans if orphans else '(none)'}")
    print(f"  Over-linked: {len(overlinked)} {overlinked if overlinked else '(none)'}")
    
    # Show missing reciprocals
    print("\n  Missing Reciprocals:")
    for zid, audit in batch_results.items():
        for gap in audit.missing_relations:
            if gap.source == 'reciprocal':
                print(f"    - {zid} missing {gap.relation_type} to {gap.target_id}")
    print()


def test_relation_discovery():
    """Test discovery of missing relations"""
    print("=" * 60)
    print("TEST: RELATION DISCOVERY")
    print("=" * 60)
    
    # Simulate existing zettels with similar tags
    existing_zettels_list = [
        TestZettel("EXISTING001", "HTTP Protocol", 
                   ["http", "protocol", "networking"], []),
        TestZettel("EXISTING002", "API Gateway", 
                   ["api", "gateway", "microservices"], []),
        TestZettel("EXISTING003", "GraphQL vs REST", 
                   ["api", "rest", "graphql", "comparison"], [])
    ]
    
    # Convert to dict for RelationChecker
    existing = {z.id: z for z in existing_zettels_list}
    existing["DISC002"] = TestZettel("DISC002", "API Documentation", ["api", "docs"], [])
    
    checker = RelationChecker(existing)
    
    # Zettel that should have more relations based on tags
    discoverable = TestZettel(
        id="DISC001",
        title="REST API Design",
        tags=["api", "rest", "http", "web-services"],
        references=[("related-to", "DISC002")]
    )
    
    audit = checker.audit_zettel(discoverable)
    
    print(f"Zettel: {discoverable.title} ({discoverable.id})")
    print(f"  Current Relations: {audit.current_relation_count}")
    print(f"  Discovered Gaps: {len(audit.missing_relations)}")
    
    if audit.missing_relations:
        print("\n  Suggested Relations:")
        for gap in audit.missing_relations[:5]:  # Show top 5
            print(f"    - {gap.relation_type} → {gap.target_id or '(new zettel needed)'}")
            print(f"      Confidence: {gap.confidence:.2f}")
            print(f"      Reason: {gap.reason}")
    
    # Generate research queries
    research_queries = checker.generate_research_queries(audit)
    if research_queries:
        print("\n  Internet Research Queries:")
        for query, purpose in research_queries[:3]:
            print(f"    - Query: {query}")
            print(f"      Purpose: {purpose}")
    print()


def test_validator_integration():
    """Test integration with zettel validator"""
    print("=" * 60)
    print("TEST: VALIDATOR INTEGRATION")
    print("=" * 60)
    
    # Create a validator with existing context
    validator = ZettelValidator(
        timezone="+00:00",
        existing_tags={'api', 'rest', 'http', 'design'},
        existing_ids={'TEST001', 'TEST002', 'TEST003'}
    )
    
    # Test content with varying relation counts
    test_cases = [
        ("Orphan", "+related-to::TEST001"),
        ("Optimal", "+related-to::TEST001\n+broader-than::TEST002\n+exemplifies::TEST003"),
        ("Over-linked", "\n".join([f"+related-to::TEST{i:03d}" for i in range(10)]))
    ]
    
    for name, references in test_cases:
        content = f"""# Test Zettel {name}
tags:: api, rest

## Core Content
This is test content.

## References
{references}
"""
        result = validator.validate_zettel(content)
        
        print(f"{name} Zettel:")
        print(f"  Valid: {result.valid}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Warnings: {len(result.warnings)}")
        
        if result.warnings:
            for warning in result.warnings:
                if "relation" in warning.lower() or "orphan" in warning.lower():
                    print(f"    - {warning}")
        print()


def main():
    """Run all relation system tests"""
    print("\n" + "=" * 60)
    print(" RELATION DISCOVERY SYSTEM TEST SUITE")
    print("=" * 60 + "\n")
    
    test_orphan_detection()
    test_optimal_relations()
    test_over_linked()
    test_batch_audit()
    test_relation_discovery()
    test_validator_integration()
    
    print("=" * 60)
    print(" ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
