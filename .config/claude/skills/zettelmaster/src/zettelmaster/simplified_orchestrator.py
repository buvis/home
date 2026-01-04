"""Simplified Orchestrator - Uses Claude Code's Task tool for sub-agent execution."""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from zettelmaster.config import system_config
from zettelmaster.directory_scanner import DirectoryScanner
from zettelmaster.zettel_parser import ZettelParser, Zettel
from zettelmaster.toon_converter import TOONConverter
from zettelmaster.zettel_validator import ZettelValidator
from zettelmaster.file_manager import FileManager
from zettelmaster.workflow_state import WorkflowStateManager, WorkflowPhase
from zettelmaster.llm_noise_filter import LLMNoiseFilter
from zettelmaster.relation_checker import RelationChecker, RelationAudit


class SimplifiedOrchestrator:
    """Orchestrates Zettelkasten creation using Claude Code's Task tool."""

    PHASE_INPUT_RETENTION = 50
    PHASE_OUTPUT_RETENTION = 50
    REPORT_RETENTION = 20

    def __init__(
        self,
        inbox_dir: Path,
        synthetic_dir: Path,
        processed_dir: Path
    ):
        """Initialize orchestrator with directories."""
        self.inbox_dir = Path(inbox_dir)
        self.synthetic_dir = Path(synthetic_dir)
        self.processed_dir = Path(processed_dir)

        # Initialize components
        self.scanner = DirectoryScanner(inbox_dir)
        self.parser = ZettelParser(synthetic_dir, processed_dir, inbox_dir)
        self.toon_converter = TOONConverter()
        self.file_manager = FileManager(synthetic_dir, processed_dir, timezone_offset=system_config.TIMEZONE_OFFSET)
        self.llm_filter = LLMNoiseFilter()  # LLM-based noise filter
        self.relation_checker = RelationChecker(self.parser.zettels)  # Relation discovery

        # State management
        state_dir = synthetic_dir / '.workflow_state'
        self.state_manager = WorkflowStateManager(state_dir)

        # Parse existing zettels for context
        self.existing_context = self._load_existing_context()

    def _load_existing_context(self) -> Dict:
        """Load existing zettel context."""
        synthetic_count = self.parser.scan_directory()
        processed_count = self.parser.scan_processed_directory()

        return {
            'synthetic_count': synthetic_count,
            'processed_count': processed_count,
            'total_zettels': synthetic_count + processed_count,
            'existing_tags': list(self.parser.get_all_tags())[:100],
            'existing_ids': list(self.parser.zettels.keys())[:50] + list(self.parser.processed_zettels.keys())[:50]
        }

    def prepare_phase_1_extraction(self, directories: List[Path]) -> Dict:
        """Prepare data for Phase 1 extraction sub-agent with LLM filtering."""
        extraction_data = {
            'phase': 'extraction',
            'instruction': 'EXTRACT ONLY CONCRETE FACTS - BE EXTREMELY AGGRESSIVE IN FILTERING',
            'directories': []
        }

        for dir_path in directories:
            try:
                # Scan directory mechanically
                content = self.scanner.scan_directory(dir_path)
                flat = self.scanner.get_flat_content(content)
                
                # Prepare content for LLM filtering
                # Instead of regex filtering, we'll pass raw content with instructions
                rel_path = dir_path.relative_to(self.inbox_dir) if dir_path != self.inbox_dir else Path('.')
                
                # Create a sample for LLM processing
                content_sample = {}
                for file_path, text in list(flat['all_text'].items())[:5]:  # Limit to 5 files
                    # Take first 500 chars of each file
                    content_sample[file_path] = text[:500]
                
                extraction_data['directories'].append({
                    'path': str(rel_path),
                    'raw_content_sample': content_sample,
                    'full_content_available': len(flat['all_text']),
                    'metadata': {
                        'text_files': len(flat['all_text']),
                        'images': len(flat['all_images']),
                        'total_words': sum(len(text.split()) for text in flat['all_text'].values())
                    }
                })

            except Exception as e:
                print(f"Error scanning {dir_path}: {e}")

        # Add LLM filtering instructions
        extraction_data['filtering_prompt'] = self.llm_filter._create_extraction_phase_prompt(extraction_data)
        
        # Add existing context
        extraction_data['existing_context'] = self.existing_context

        # Save for sub-agent
        self._save_phase_input('extraction', extraction_data)

        return extraction_data

    def prepare_phase_2_planning(self, extraction_results: str) -> Dict:
        """Prepare data for Phase 2 planning based on extraction results."""
        planning_data = {
            'phase': 'planning',
            'extraction_results': extraction_results,
            'existing_context': self.existing_context
        }

        # Save for sub-agent
        self._save_phase_input('planning', planning_data)

        return planning_data

    def prepare_phase_3_creation(self, planning_results: str) -> Dict:
        """Prepare data for Phase 3 zettel creation."""
        creation_data = {
            'phase': 'creation',
            'planning_results': planning_results,
            'existing_context': self.existing_context
        }

        self._save_phase_input('creation', creation_data)
        return creation_data

    def prepare_phase_3_5_relation_audit(self, created_zettels: str) -> Dict:
        """Prepare data for Phase 3.5 intra-batch relation audit.
        
        This phase audits relations within the batch of newly created zettels
        to ensure they are well-connected before organization.
        """
        # Parse created zettels from TOON
        zettels_data = self._extract_validated_zettels(created_zettels)
        
        # Perform batch audit
        audit_results = []
        relation_gaps = []
        
        for zettel_dict in zettels_data:
            # Convert dict to Zettel object for audit
            zettel = self._dict_to_zettel(zettel_dict)
            
            # Audit this zettel for missing relations
            audit = self.relation_checker.audit_zettel(zettel)
            
            audit_results.append({
                'zettel_id': audit.zettel_id,
                'relation_count': audit.current_relation_count,
                'is_orphan': audit.is_orphan,
                'over_linked': audit.over_linked,
                'missing_count': len(audit.missing_relations),
                'warnings': audit.warnings
            })
            
            # Collect gaps for AI processing
            for gap in audit.missing_relations:
                if gap.confidence >= self.relation_checker.MEDIUM_CONFIDENCE:
                    relation_gaps.append({
                        'zettel_id': gap.zettel_id,
                        'relation': gap.relation_type,
                        'target': gap.target_id,
                        'confidence': gap.confidence,
                        'reason': gap.reason
                    })
        
        # Prepare batch analysis
        batch_audit = self.relation_checker.audit_batch([self._dict_to_zettel(z) for z in zettels_data])
        
        relation_audit_data = {
            'phase': 'relation_audit',
            'created_zettels': created_zettels,
            'audit_results': audit_results,
            'relation_gaps': relation_gaps,
            'batch_metrics': {
                'total_zettels': len(zettels_data),
                'orphans': sum(1 for a in audit_results if a['is_orphan']),
                'over_linked': sum(1 for a in audit_results if a['over_linked']),
                'total_missing': len(relation_gaps)
            },
            'existing_context': self.existing_context
        }
        
        self._save_phase_input('relation_audit', relation_audit_data)
        return relation_audit_data

    def prepare_phase_4_organization(self, created_zettels: str) -> Dict:
        """Prepare data for Phase 4 organization."""
        organization_data = {
            'phase': 'organization',
            'created_zettels': created_zettels
        }

        self._save_phase_input('organization', organization_data)
        return organization_data

    def prepare_phase_5_integration(self, organization_results: str, created_zettels: str) -> Dict:
        """Prepare data for Phase 5 integration with enhanced semantic analysis.
        
        This phase not only integrates new zettels with existing ones but also:
        1. Performs semantic analysis to find potential cross-connections
        2. Identifies knowledge gaps that could be filled with relations
        3. Suggests transitive and hierarchical relations
        """
        # Parse created zettels for semantic analysis
        zettels_data = self._extract_validated_zettels(created_zettels)
        
        # Collect existing zettels for semantic comparison
        existing_sample = self._get_existing_sample()
        
        # Perform semantic analysis for each new zettel
        semantic_suggestions = []
        for new_zettel in zettels_data:
            zettel_obj = self._dict_to_zettel(new_zettel)
            
            # Find semantic candidates among existing zettels
            candidates = []
            for existing_id, existing_info in existing_sample.items():
                # Simple tag-based similarity for now
                common_tags = set(new_zettel.get('tags', [])) & set(existing_info.get('tags', []))
                if common_tags:
                    candidates.append({
                        'existing_id': existing_id,
                        'existing_title': existing_info.get('title'),
                        'common_tags': list(common_tags),
                        'similarity_score': len(common_tags) / max(
                            len(new_zettel.get('tags', [])), 
                            len(existing_info.get('tags', [])),
                            1
                        )
                    })
            
            # Sort by similarity and take top candidates
            candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
            top_candidates = candidates[:5]
            
            if top_candidates:
                semantic_suggestions.append({
                    'zettel_id': new_zettel.get('id'),
                    'zettel_title': new_zettel.get('title'),
                    'potential_connections': top_candidates
                })
        
        # Analyze for hierarchical relations (broader/narrower)
        hierarchy_suggestions = self._analyze_hierarchical_relations(zettels_data, existing_sample)
        
        # Analyze for transitive relations
        transitive_suggestions = self._analyze_transitive_relations(zettels_data)
        
        integration_data = {
            'phase': 'integration',
            'organization_results': organization_results,
            'created_zettels': created_zettels,
            'existing_zettels_sample': existing_sample,
            'semantic_analysis': {
                'semantic_suggestions': semantic_suggestions,
                'hierarchy_suggestions': hierarchy_suggestions,
                'transitive_suggestions': transitive_suggestions,
                'total_suggestions': len(semantic_suggestions) + len(hierarchy_suggestions) + len(transitive_suggestions)
            }
        }

        self._save_phase_input('integration', integration_data)
        return integration_data

    def prepare_phase_5_5_research(self, integration_results: str, relation_audit_results: str) -> Dict:
        """Prepare data for Phase 5.5 internet research to fill knowledge gaps.
        
        This phase uses internet research to:
        1. Fill gaps in relations identified during audit
        2. Find missing context for orphan zettels
        3. Discover connections not evident in source material
        4. Enrich zettels with complementary knowledge
        """
        # Parse results from previous phases
        integration_data = self._parse_toon_results(integration_results)
        audit_data = self._parse_toon_results(relation_audit_results)
        
        # Identify research needs
        research_queries = []
        
        # From relation audit - orphan zettels need context
        if 'audit_results' in audit_data:
            for audit in audit_data['audit_results']:
                if audit.get('is_orphan'):
                    zettel_id = audit.get('zettel_id')
                    # Find the zettel to get its title/content for research
                    research_queries.append({
                        'type': 'orphan_context',
                        'zettel_id': zettel_id,
                        'priority': 'high',
                        'query': f"Find related concepts and connections for orphan zettel {zettel_id}",
                        'expected_relations': ['related-to', 'broader-than', 'part-of']
                    })
        
        # From relation gaps - missing reciprocals or expected relations
        if 'relation_gaps' in audit_data:
            for gap in audit_data['relation_gaps'][:5]:  # Limit to top 5 gaps
                research_queries.append({
                    'type': 'missing_relation',
                    'zettel_id': gap.get('zettel_id'),
                    'relation': gap.get('relation'),
                    'target': gap.get('target'),
                    'priority': 'medium',
                    'query': f"Research connection between {gap.get('zettel_id')} and {gap.get('target')} for relation {gap.get('relation')}",
                    'confidence': gap.get('confidence', 0.5)
                })
        
        # From semantic analysis - low confidence suggestions need validation
        if 'semantic_analysis' in integration_data:
            semantic = integration_data['semantic_analysis']
            for suggestion in semantic.get('semantic_suggestions', [])[:3]:  # Top 3
                if suggestion.get('potential_connections'):
                    top_connection = suggestion['potential_connections'][0]
                    if top_connection.get('similarity_score', 0) < 0.5:
                        research_queries.append({
                            'type': 'validate_connection',
                            'zettel_id': suggestion.get('zettel_id'),
                            'target_id': top_connection.get('existing_id'),
                            'priority': 'low',
                            'query': f"Validate potential connection between {suggestion.get('zettel_title')} and {top_connection.get('existing_title')}",
                            'similarity_score': top_connection.get('similarity_score')
                        })
        
        # Group queries by priority
        high_priority = [q for q in research_queries if q.get('priority') == 'high']
        medium_priority = [q for q in research_queries if q.get('priority') == 'medium']
        low_priority = [q for q in research_queries if q.get('priority') == 'low']
        
        research_data = {
            'phase': 'research',
            'research_queries': {
                'high_priority': high_priority[:3],  # Limit high priority to 3
                'medium_priority': medium_priority[:5],  # Limit medium to 5
                'low_priority': low_priority[:2]  # Limit low to 2
            },
            'total_queries': len(high_priority) + len(medium_priority) + len(low_priority),
            'research_limits': {
                'max_queries': 10,
                'time_per_query': '30 seconds',
                'max_results_per_query': 3
            },
            'context': {
                'integration_summary': integration_data.get('raw_content', '')[:500],
                'audit_summary': audit_data.get('raw_content', '')[:500]
            }
        }
        
        self._save_phase_input('research', research_data)
        return research_data

    def prepare_phase_6_validation(self, created_zettels: str, integration_results: str) -> Dict:
        """Prepare data for Phase 6 validation."""
        validation_data = {
            'phase': 'validation',
            'created_zettels': created_zettels,
            'integration_results': integration_results
        }

        self._save_phase_input('validation', validation_data)
        return validation_data

    def process_phase_results(self, phase: str, results: str) -> Dict:
        """Process results from a phase sub-agent."""
        # Parse results (expecting TOON format)
        parsed_results = self._parse_toon_results(results)

        # Save phase output
        output_dir = self.synthetic_dir / '.phase_outputs'
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f'phase_{phase}_{timestamp}.toon'
        output_file.write_text(results)
        self._prune_directory(output_dir, 'phase_*_*.toon', self.PHASE_OUTPUT_RETENTION)

        # Update workflow state
        if self.state_manager.current_state:
            phase_enum = self._get_phase_enum(phase)
            self.state_manager.complete_phase(phase_enum, parsed_results)

        return parsed_results

    def finalize_zettels(self, validation_results: str) -> Dict:
        """Finalize and write validated zettels to files."""
        # Parse validation results
        validated_zettels = self._extract_validated_zettels(validation_results)

        results = {
            'files_created': [],
            'errors': []
        }

        # Initialize validator
        all_ids = set(z.get('id', '') for z in validated_zettels)
        all_tags = set()
        for zettel in validated_zettels:
            all_tags.update(zettel.get('tags', []))

        # Format timezone string for validator
        tz_offset = system_config.TIMEZONE_OFFSET
        offset_hours = int(tz_offset)
        offset_minutes = int((abs(tz_offset) % 1) * 60)
        sign = '+' if tz_offset >= 0 else '-'
        tz_str = f"{sign}{abs(offset_hours):02d}:{offset_minutes:02d}"
        
        validator = ZettelValidator(
            timezone=tz_str,
            existing_tags=all_tags | self.parser.get_all_tags(),
            existing_ids=all_ids | set(self.parser.zettels.keys()) | set(self.parser.processed_zettels.keys())
        )

        # Write each validated zettel
        for zettel in validated_zettels:
            try:
                # Validate structure
                errors = validator.validate_structure(
                    zettel.get('id', ''),
                    zettel.get('title', ''),
                    zettel.get('tags', []),
                    zettel.get('body', ''),
                    zettel.get('relations', {})
                )

                if not errors:
                    file_path = self.file_manager.save_zettel(zettel)
                    results['files_created'].append({
                        'id': zettel['id'],
                        'path': str(file_path)
                    })
                else:
                    results['errors'].append({
                        'id': zettel.get('id', 'unknown'),
                        'errors': errors
                    })

            except Exception as e:
                results['errors'].append({
                    'id': zettel.get('id', 'unknown'),
                    'error': str(e)
                })

        # Save final report
        self._save_final_report(results)

        return results

    def _save_phase_input(self, phase: str, data: Dict):
        """Save phase input data for debugging."""
        input_dir = self.synthetic_dir / '.phase_inputs'
        input_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Convert to TOON for efficiency
        toon_content = self._dict_to_toon(data, phase)

        input_file = input_dir / f'phase_{phase}_input_{timestamp}.toon'
        input_file.write_text(toon_content)
        self._prune_directory(input_dir, 'phase_*_input_*.toon', self.PHASE_INPUT_RETENTION)

    def _dict_to_toon(self, data: Dict, root_key: str) -> str:
        """Convert dictionary to TOON format."""
        lines = [root_key]

        def format_value(value, indent=2):
            if isinstance(value, dict):
                result = []
                for k, v in value.items():
                    result.append(' ' * indent + k)
                    if isinstance(v, (dict, list)):
                        result.extend(format_value(v, indent + 2))
                    else:
                        result.append(' ' * (indent + 2) + str(v))
                return result
            elif isinstance(value, list):
                result = []
                for item in value[:10]:  # Limit to first 10 items
                    if isinstance(item, dict):
                        result.extend(format_value(item, indent))
                    else:
                        result.append(' ' * indent + '- ' + str(item))
                return result
            else:
                return [' ' * indent + str(value)]

        for key, value in data.items():
            lines.append(f'  {key}')
            lines.extend(format_value(value, 4))

        return '\n'.join(lines)

    def _parse_toon_results(self, toon_content: str) -> Dict:
        """Parse TOON results back to dict."""
        data: Dict[str, Any] = {}

        if not toon_content or not toon_content.strip():
            data['raw_content'] = toon_content or ''
            return data

        try:
            parsed = self.toon_converter.toon_to_dict(toon_content)

            if isinstance(parsed, dict) and len(parsed) == 1:
                root_key, value = next(iter(parsed.items()))
                if isinstance(value, dict):
                    data.update(value)
                    data['__root__'] = root_key
                else:
                    data[root_key] = value
            elif isinstance(parsed, dict):
                data.update(parsed)
            else:
                data['parsed'] = parsed
        except Exception as exc:
            data['parse_error'] = str(exc)

        data['raw_content'] = toon_content
        return data

    def _extract_validated_zettels(self, validation_results: str) -> List[Dict]:
        """Extract validated zettels from results."""
        # Parse TOON results to extract zettels
        # This would be implemented based on actual TOON structure
        return self.toon_converter.toon_to_proposals(validation_results)

    def _get_existing_sample(self) -> Dict:
        """Get sample of existing zettels for integration."""
        sample = {}

        # Sample synthetic zettels
        for zid, zettel in list(self.parser.zettels.items())[:10]:
            sample[zid] = {
                'title': zettel.get('title', 'Untitled'),
                'tags': zettel.get('tags', [])[:5]
            }

        return sample

    def _get_phase_enum(self, phase: str) -> WorkflowPhase:
        """Convert phase string to enum."""
        phase_map = {
            'extraction': WorkflowPhase.EXTRACTION,
            'planning': WorkflowPhase.PLANNING,
            'creation': WorkflowPhase.CREATION,
            'relation_audit': WorkflowPhase.CREATION,  # Map to creation phase for now
            'organization': WorkflowPhase.ORGANIZATION,
            'integration': WorkflowPhase.INTEGRATION,
            'research': WorkflowPhase.INTEGRATION,  # Map to integration phase
            'validation': WorkflowPhase.VALIDATION
        }
        return phase_map.get(phase, WorkflowPhase.NOT_STARTED)
    
    def _dict_to_zettel(self, zettel_dict: Dict) -> Zettel:
        """Convert zettel dictionary to Zettel object for relation checking."""
        # Create a minimal Zettel object for relation checking
        class SimpleZettel:
            def __init__(self, data):
                self.id = data.get('id', '')
                self.title = data.get('title', '')
                self.tags = data.get('tags', [])
                self.body = data.get('body', '')
                self.references = data.get('references', [])
                self.relations = data.get('relations', {})
                
                # Parse references from body if not explicitly provided
                if not self.references and self.body:
                    ref_pattern = r'\+([a-z-]+)::(\S+)'
                    self.references = re.findall(ref_pattern, self.body)
        
        return SimpleZettel(zettel_dict)
    
    def _analyze_hierarchical_relations(self, new_zettels: List[Dict], existing_zettels: Dict) -> List[Dict]:
        """Analyze potential broader-than/narrower-than relations.
        
        Looks for:
        - General vs specific concepts based on title/tag analysis
        - Abstract vs concrete implementations
        - Category vs instance relationships
        """
        suggestions = []
        
        for zettel in new_zettels:
            zettel_tags = set(zettel.get('tags', []))
            zettel_title = zettel.get('title', '').lower()
            
            # Check for potential parent/child relationships
            for existing_id, existing_info in existing_zettels.items():
                existing_tags = set(existing_info.get('tags', []))
                existing_title = existing_info.get('title', '').lower()
                
                # Simple heuristic: if one has more specific tags, it's narrower
                if zettel_tags and existing_tags:
                    if zettel_tags < existing_tags:  # zettel_tags is subset
                        suggestions.append({
                            'from_id': zettel.get('id'),
                            'to_id': existing_id,
                            'relation': 'broader-than',
                            'reason': 'Tag subset indicates more general concept'
                        })
                    elif existing_tags < zettel_tags:  # existing_tags is subset
                        suggestions.append({
                            'from_id': zettel.get('id'),
                            'to_id': existing_id,
                            'relation': 'narrower-than',
                            'reason': 'Tag superset indicates more specific concept'
                        })
                
                # Title-based hierarchy detection (simple keywords)
                if 'general' in zettel_title and 'specific' in existing_title:
                    suggestions.append({
                        'from_id': zettel.get('id'),
                        'to_id': existing_id,
                        'relation': 'broader-than',
                        'reason': 'Title indicates generalization'
                    })
                elif 'specific' in zettel_title and 'general' in existing_title:
                    suggestions.append({
                        'from_id': zettel.get('id'),
                        'to_id': existing_id,
                        'relation': 'narrower-than',
                        'reason': 'Title indicates specialization'
                    })
        
        return suggestions
    
    def _analyze_transitive_relations(self, new_zettels: List[Dict]) -> List[Dict]:
        """Analyze potential transitive relation chains.
        
        For relations like broader-than, narrower-than, part-of, caused-by,
        if A->B and B->C exist, suggest A->C.
        """
        suggestions = []
        transitive_types = {'broader-than', 'narrower-than', 'part-of', 'caused-by', 'follows'}
        
        # Build relation graph from new zettels
        relations_map = {}
        for zettel in new_zettels:
            zettel_id = zettel.get('id')
            relations = zettel.get('relations', {})
            
            for rel_type, targets in relations.items():
                if rel_type in transitive_types:
                    if zettel_id not in relations_map:
                        relations_map[zettel_id] = {}
                    relations_map[zettel_id][rel_type] = targets if isinstance(targets, list) else [targets]
        
        # Find transitive chains
        for source_id, source_rels in relations_map.items():
            for rel_type, direct_targets in source_rels.items():
                for intermediate_id in direct_targets:
                    if intermediate_id in relations_map:
                        intermediate_rels = relations_map.get(intermediate_id, {})
                        if rel_type in intermediate_rels:
                            # Found transitive chain: source -> intermediate -> final
                            for final_id in intermediate_rels[rel_type]:
                                if final_id not in direct_targets:  # Not already connected
                                    suggestions.append({
                                        'from_id': source_id,
                                        'to_id': final_id,
                                        'via_id': intermediate_id,
                                        'relation': rel_type,
                                        'reason': f'Transitive chain via {intermediate_id}'
                                    })
        
        return suggestions

    def _save_final_report(self, results: Dict):
        """Save final processing report."""
        report_dir = self.synthetic_dir / '.reports'
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f'final_report_{timestamp}.json'

        report = {
            'timestamp': datetime.now().isoformat(),
            'existing_context': self.existing_context,
            'files_created': results['files_created'],
            'errors': results['errors'],
            'summary': {
                'total_created': len(results['files_created']),
                'total_errors': len(results['errors']),
                'success_rate': len(results['files_created']) / (len(results['files_created']) + len(results['errors'])) if results['files_created'] or results['errors'] else 0
            }
        }

        report_file.write_text(json.dumps(report, indent=2))
        self._prune_directory(report_dir, 'final_report_*.json', self.REPORT_RETENTION)

    def _prune_directory(self, directory: Path, pattern: str, retain: int):
        """Keep only the newest `retain` files in a directory."""
        if retain <= 0 or not directory.exists():
            return

        files = sorted(
            (path for path in directory.glob(pattern) if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        for stale in files[retain:]:
            try:
                stale.unlink()
            except FileNotFoundError:
                continue
