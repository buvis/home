#!/usr/bin/env python
"""
Enhanced ZettelMaster processor with all new capabilities integrated.
Demonstrates semantic analysis, document extraction, and automatic reciprocal links.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
import time
import json

# Import core modules
from zettelmaster.zettel_parser import ZettelParser, Zettel
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.zettel_generator import ZettelGenerator
from zettelmaster.directory_scanner import DirectoryScanner
from zettelmaster.semantic_analyzer import SemanticAnalyzer, SimilarityResult
from zettelmaster.logging_config import setup_logging, get_logger
from zettelmaster.config import zettel_config, system_config


class EnhancedZettelProcessor:
    """
    Enhanced processor integrating all new capabilities:
    - Semantic duplicate detection
    - Automatic reciprocal links
    - Document extraction (PDF/DOCX)
    - Tag suggestions
    - Structured logging
    """
    
    def __init__(
        self,
        synthetic_dir: Path = Path("synthetic"),
        processed_dir: Path = Path("processed"),
        inbox_dir: Path = Path("inbox"),
        log_level: str = "INFO"
    ):
        # Setup logging first
        setup_logging(log_level=log_level, structured=True)
        self.logger = get_logger(__name__)
        self.logger.info("Initializing Enhanced Zettel Processor")
        
        # Initialize directories
        self.synthetic_dir = synthetic_dir
        self.processed_dir = processed_dir
        self.inbox_dir = inbox_dir
        
        # Initialize components
        self.parser = ZettelParser()
        self.semantic_analyzer = SemanticAnalyzer()
        self.scanner = DirectoryScanner(inbox_dir)
        
        # Load existing zettels
        self._load_existing_zettels()
        
        # Initialize validator with existing IDs
        self.validator = ZettelValidator(
            existing_ids=self.parser.existing_ids,
            existing_tags=list(self.parser.tags.keys())
        )
        
        self.generator = ZettelGenerator()
        
        self.logger.info(
            f"Loaded {len(self.parser.zettels)} existing zettels",
            extra={'zettel_count': len(self.parser.zettels)}
        )
    
    def _load_existing_zettels(self):
        """Load existing zettels from synthetic and processed directories."""
        start_time = time.time()
        
        if self.synthetic_dir.exists():
            self.parser.load_from_directory(self.synthetic_dir)
            self.logger.info(f"Loaded synthetic zettels from {self.synthetic_dir}")
        
        if self.processed_dir.exists():
            self.parser.load_from_directory(self.processed_dir, readonly=True)
            self.logger.info(f"Loaded processed zettels from {self.processed_dir}")
        
        duration = (time.time() - start_time) * 1000
        self.logger.timing("load_existing_zettels", duration)
    
    def process_inbox_enhanced(
        self,
        extract_documents: bool = True,
        check_duplicates: bool = True,
        add_reciprocals: bool = True,
        suggest_tags: bool = True,
        duplicate_threshold: float = 0.85
    ) -> Dict:
        """
        Process inbox with all enhanced features.
        
        Args:
            extract_documents: Extract content from PDFs/DOCX
            check_duplicates: Check for semantic duplicates
            add_reciprocals: Automatically add reciprocal links
            suggest_tags: Provide tag suggestions based on similarity
            duplicate_threshold: Similarity threshold for duplicate detection
        
        Returns:
            Processing report with statistics and findings
        """
        self.logger.operation("process_inbox_enhanced")
        report = {
            'processed_files': 0,
            'documents_extracted': 0,
            'duplicates_found': [],
            'reciprocals_added': {},
            'tag_suggestions': {},
            'errors': []
        }
        
        # Scan inbox with document extraction
        self.logger.info("Scanning inbox directory")
        content = self.scanner.scan_directory_enhanced(
            extract_documents=extract_documents,
            enable_ocr=False  # OCR disabled by default (slow)
        )
        
        # Process extraction stats
        if 'extraction_stats' in content.metadata:
            stats = content.metadata['extraction_stats']
            report['documents_extracted'] = stats['pdfs_extracted'] + stats['docx_extracted']
            self.logger.info(
                f"Extracted {report['documents_extracted']} documents",
                extra={'extraction_stats': stats}
            )
        
        # Process each text file (including extracted documents)
        for file_path, text_content in content.text_files.items():
            self.logger.info(f"Processing: {file_path}")
            report['processed_files'] += 1
            
            try:
                # Create temporary zettel for analysis
                temp_zettel = self._create_temp_zettel(file_path, text_content)
                
                # Check for semantic duplicates
                if check_duplicates and self.semantic_analyzer.is_available():
                    duplicates = self.semantic_analyzer.find_semantic_duplicates(
                        temp_zettel,
                        self.parser.zettels,
                        threshold=duplicate_threshold
                    )
                    
                    if duplicates:
                        dup_info = {
                            'file': file_path,
                            'duplicates': [
                                {
                                    'id': d.target_id,
                                    'title': d.target_title,
                                    'similarity': f"{d.similarity_score:.2%}",
                                    'type': d.similarity_type
                                }
                                for d in duplicates
                            ]
                        }
                        report['duplicates_found'].append(dup_info)
                        
                        self.logger.warning(
                            f"Potential duplicates found for {file_path}",
                            extra={'duplicate_count': len(duplicates)}
                        )
                
                # Suggest tags
                if suggest_tags and self.semantic_analyzer.is_available():
                    suggestions = self.semantic_analyzer.suggest_tags_semantic(
                        text_content,
                        self.parser.zettels,
                        max_suggestions=5
                    )
                    
                    if suggestions:
                        report['tag_suggestions'][file_path] = [
                            {'tag': tag, 'confidence': f"{conf:.2%}"}
                            for tag, conf in suggestions
                        ]
                        
                        self.logger.info(
                            f"Generated {len(suggestions)} tag suggestions",
                            extra={'file': file_path}
                        )
                
            except Exception as e:
                error_msg = f"Error processing {file_path}: {e}"
                report['errors'].append(error_msg)
                self.logger.error(error_msg, exc_info=True)
        
        # Process reciprocal links for existing zettels
        if add_reciprocals:
            self.logger.info("Checking and adding reciprocal links")
            reciprocals_report = self._process_reciprocal_links()
            report['reciprocals_added'] = reciprocals_report
        
        # Generate final report
        self.logger.info("Processing complete", extra={'report_summary': {
            'files': report['processed_files'],
            'extracted': report['documents_extracted'],
            'duplicates': len(report['duplicates_found']),
            'errors': len(report['errors'])
        }})
        
        return report
    
    def _create_temp_zettel(self, file_path: str, content: str) -> Zettel:
        """Create a temporary Zettel object for analysis."""
        # Extract title from first line or filename
        lines = content.split('\n')
        title = lines[0].strip('#').strip() if lines else Path(file_path).stem
        
        # Generate temporary ID
        temp_id = self.validator.generate_unique_id(self.parser.existing_ids)
        
        return Zettel(
            id=temp_id,
            title=title[:100],  # Limit title length
            body=content[:5000],  # Limit body for analysis
            tags=[],  # No tags yet
            type='note',
            date=None,
            publish=False,
            processed=False,
            synthetic=True,
            relations={},
            references={}
        )
    
    def _process_reciprocal_links(self) -> Dict:
        """Check and add missing reciprocal links."""
        reciprocals_added = {}
        
        for zettel_id, zettel in self.parser.zettels.items():
            if zettel.readonly:  # Skip processed zettels
                continue
            
            zettel_path = self.synthetic_dir / f"{zettel_id}.md"
            if not zettel_path.exists():
                continue
            
            # Add reciprocals (auto_fix=True)
            added = self.validator.add_reciprocal_links(
                zettel_path,
                auto_fix=True,
                synthetic_dir=self.synthetic_dir
            )
            
            if added:
                reciprocals_added[zettel_id] = added
                self.logger.info(
                    f"Added reciprocals for {zettel_id}",
                    extra={'reciprocals': added}
                )
        
        return reciprocals_added
    
    def check_semantic_health(self) -> Dict:
        """
        Perform comprehensive semantic health check on the zettel collection.
        
        Returns:
            Health report with findings and recommendations
        """
        self.logger.operation("semantic_health_check")
        
        if not self.semantic_analyzer.is_available():
            self.logger.warning("Semantic analyzer not available")
            return {'error': 'Semantic analyzer not available'}
        
        health_report = {
            'total_zettels': len(self.parser.zettels),
            'potential_duplicates': [],
            'orphaned_zettels': [],
            'missing_relations': [],
            'tag_consistency': {},
            'recommendations': []
        }
        
        # Check for duplicates across entire collection
        self.logger.info("Checking for semantic duplicates")
        checked_pairs = set()
        
        for id1, z1 in self.parser.zettels.items():
            for id2, z2 in self.parser.zettels.items():
                if id1 >= id2:  # Avoid checking same pair twice
                    continue
                
                pair_key = tuple(sorted([id1, id2]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                # Calculate similarity
                combined1 = f"{z1.title}. {z1.body}"
                combined2 = f"{z2.title}. {z2.body}"
                
                emb1 = self.semantic_analyzer.get_embedding(combined1, cache_key=f"health_{id1}")
                emb2 = self.semantic_analyzer.get_embedding(combined2, cache_key=f"health_{id2}")
                
                if emb1 is not None and emb2 is not None:
                    similarity = self.semantic_analyzer.cosine_similarity(emb1, emb2)
                    
                    if similarity > 0.9:  # Very high similarity
                        health_report['potential_duplicates'].append({
                            'id1': id1,
                            'title1': z1.title,
                            'id2': id2,
                            'title2': z2.title,
                            'similarity': f"{similarity:.2%}"
                        })
        
        # Find orphaned zettels (could benefit from more relations)
        for zettel_id, zettel in self.parser.zettels.items():
            total_relations = sum(len(ids) for ids in zettel.relations.values())
            
            if total_relations < 2:
                # Find potential relations
                related = self.semantic_analyzer.find_related_by_embedding(
                    zettel,
                    self.parser.zettels,
                    max_results=3,
                    min_similarity=0.6
                )
                
                if related:
                    health_report['orphaned_zettels'].append({
                        'id': zettel_id,
                        'title': zettel.title,
                        'current_relations': total_relations,
                        'suggested_relations': [
                            {
                                'id': r.target_id,
                                'title': r.target_title,
                                'similarity': f"{r.similarity_score:.2%}"
                            }
                            for r in related
                        ]
                    })
        
        # Generate recommendations
        if health_report['potential_duplicates']:
            health_report['recommendations'].append(
                f"Review {len(health_report['potential_duplicates'])} potential duplicate pairs"
            )
        
        if health_report['orphaned_zettels']:
            health_report['recommendations'].append(
                f"Add relations to {len(health_report['orphaned_zettels'])} orphaned zettels"
            )
        
        self.logger.info("Health check complete", extra={'summary': {
            'duplicates': len(health_report['potential_duplicates']),
            'orphans': len(health_report['orphaned_zettels'])
        }})
        
        return health_report
    
    def save_report(self, report: Dict, filename: str = "processing_report.json"):
        """Save processing report to file."""
        report_path = Path(filename)
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Report saved to {report_path}")
        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")


def main():
    """Demonstrate enhanced processing capabilities."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced ZettelMaster Processor")
    parser.add_argument('--inbox', type=str, default='inbox', help='Inbox directory')
    parser.add_argument('--synthetic', type=str, default='synthetic', help='Synthetic directory')
    parser.add_argument('--processed', type=str, default='processed', help='Processed directory')
    parser.add_argument('--extract-docs', action='store_true', help='Extract PDF/DOCX content')
    parser.add_argument('--check-duplicates', action='store_true', help='Check for semantic duplicates')
    parser.add_argument('--add-reciprocals', action='store_true', help='Add missing reciprocal links')
    parser.add_argument('--suggest-tags', action='store_true', help='Suggest tags for new content')
    parser.add_argument('--health-check', action='store_true', help='Run semantic health check')
    parser.add_argument('--log-level', type=str, default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Initialize processor
    processor = EnhancedZettelProcessor(
        synthetic_dir=Path(args.synthetic),
        processed_dir=Path(args.processed),
        inbox_dir=Path(args.inbox),
        log_level=args.log_level
    )
    
    # Process inbox with enhanced features
    if Path(args.inbox).exists() and any(Path(args.inbox).iterdir()):
        print("\n=== Processing Inbox ===")
        report = processor.process_inbox_enhanced(
            extract_documents=args.extract_docs,
            check_duplicates=args.check_duplicates,
            add_reciprocals=args.add_reciprocals,
            suggest_tags=args.suggest_tags
        )
        
        # Display summary
        print(f"\nProcessed: {report['processed_files']} files")
        print(f"Documents extracted: {report['documents_extracted']}")
        print(f"Potential duplicates found: {len(report['duplicates_found'])}")
        print(f"Reciprocal links added: {len(report['reciprocals_added'])} zettels updated")
        
        if report['duplicates_found']:
            print("\n--- Potential Duplicates ---")
            for dup in report['duplicates_found'][:3]:  # Show first 3
                print(f"  {dup['file']}:")
                for d in dup['duplicates'][:2]:  # Show top 2 matches
                    print(f"    - {d['title']} ({d['similarity']} similarity)")
        
        if report['tag_suggestions']:
            print("\n--- Tag Suggestions ---")
            for file, tags in list(report['tag_suggestions'].items())[:3]:
                print(f"  {file}:")
                for tag in tags[:3]:
                    print(f"    - {tag['tag']} ({tag['confidence']})")
        
        # Save full report
        processor.save_report(report)
    
    # Run health check
    if args.health_check:
        print("\n=== Semantic Health Check ===")
        health = processor.check_semantic_health()
        
        print(f"\nTotal zettels: {health['total_zettels']}")
        print(f"Potential duplicates: {len(health['potential_duplicates'])}")
        print(f"Orphaned zettels: {len(health['orphaned_zettels'])}")
        
        if health['recommendations']:
            print("\nRecommendations:")
            for rec in health['recommendations']:
                print(f"  - {rec}")
        
        # Save health report
        processor.save_report(health, "health_report.json")


if __name__ == "__main__":
    main()