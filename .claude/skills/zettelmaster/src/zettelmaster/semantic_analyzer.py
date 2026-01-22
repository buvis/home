#!/usr/bin/env python
"""
Semantic analysis module for ZettelMaster.
Provides embedding-based similarity detection and tag suggestions.
"""

import logging
from typing import List, Tuple, Dict, Optional, Set
from pathlib import Path
import numpy as np
from dataclasses import dataclass
import json

# Optional imports - graceful degradation if not available
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Semantic features disabled.")
    print("Install with: pip install sentence-transformers")

from zettelmaster.config import ZettelConfig
from zettelmaster.zettel_parser import Zettel, ZettelParser

logger = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    """Result of similarity comparison between zettels."""
    source_id: str
    target_id: str
    similarity_score: float
    target_title: str
    target_tags: List[str]
    similarity_type: str  # 'title', 'body', 'combined'


class SemanticAnalyzer:
    """Analyzes semantic similarity between zettels using embeddings."""
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize the semantic analyzer.
        
        Args:
            model_name: Name of the sentence-transformers model to use.
                       Default is a lightweight, general-purpose model.
                       For better accuracy, consider 'all-mpnet-base-v2'.
        """
        self.model = None
        self.model_name = model_name
        self.embeddings_cache: Dict[str, np.ndarray] = {}
        
        if EMBEDDINGS_AVAILABLE:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"Loaded embedding model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self.model = None
    
    def is_available(self) -> bool:
        """Check if semantic analysis is available."""
        return self.model is not None
    
    def get_embedding(self, text: str, cache_key: Optional[str] = None) -> Optional[np.ndarray]:
        """
        Get embedding for text, with optional caching.
        
        Args:
            text: Text to embed
            cache_key: Optional key for caching the embedding
        
        Returns:
            Embedding vector or None if not available
        """
        if not self.is_available():
            return None
        
        # Check cache
        if cache_key and cache_key in self.embeddings_cache:
            return self.embeddings_cache[cache_key]
        
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            
            # Cache if key provided
            if cache_key:
                self.embeddings_cache[cache_key] = embedding
            
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def find_semantic_duplicates(
        self,
        new_zettel: Zettel,
        existing_zettels: Dict[str, Zettel],
        threshold: float = 0.85,
        check_title: bool = True,
        check_body: bool = True,
        max_results: int = 5
    ) -> List[SimilarityResult]:
        """
        Find semantically similar zettels that might be duplicates.
        
        Args:
            new_zettel: The zettel to check for duplicates
            existing_zettels: Dictionary of existing zettels (id -> Zettel)
            threshold: Similarity threshold (0-1) above which to consider duplicate
            check_title: Whether to check title similarity
            check_body: Whether to check body similarity
            max_results: Maximum number of similar zettels to return
        
        Returns:
            List of similar zettels sorted by similarity score (highest first)
        """
        if not self.is_available():
            logger.warning("Semantic analysis not available, falling back to title matching")
            return self._fallback_duplicate_detection(new_zettel, existing_zettels, max_results)
        
        results: List[SimilarityResult] = []
        
        # Prepare new zettel embeddings
        new_title_emb = None
        new_body_emb = None
        new_combined_emb = None
        
        if check_title:
            new_title_emb = self.get_embedding(new_zettel.title)
        
        if check_body:
            new_body_emb = self.get_embedding(new_zettel.body)
        
        # Combined embedding (weighted: title has more importance)
        combined_text = f"{new_zettel.title}. {new_zettel.title}. {new_zettel.body}"
        new_combined_emb = self.get_embedding(combined_text)
        
        # Compare with existing zettels
        for zettel_id, existing in existing_zettels.items():
            # Skip self-comparison
            if zettel_id == new_zettel.id:
                continue
            
            similarities = []
            
            # Title similarity
            if check_title and new_title_emb is not None:
                existing_title_emb = self.get_embedding(
                    existing.title,
                    cache_key=f"title_{zettel_id}"
                )
                if existing_title_emb is not None:
                    title_sim = self.cosine_similarity(new_title_emb, existing_title_emb)
                    if title_sim >= threshold:
                        similarities.append(('title', title_sim))
            
            # Body similarity
            if check_body and new_body_emb is not None:
                existing_body_emb = self.get_embedding(
                    existing.body,
                    cache_key=f"body_{zettel_id}"
                )
                if existing_body_emb is not None:
                    body_sim = self.cosine_similarity(new_body_emb, existing_body_emb)
                    if body_sim >= threshold:
                        similarities.append(('body', body_sim))
            
            # Combined similarity (most reliable)
            if new_combined_emb is not None:
                existing_combined = f"{existing.title}. {existing.title}. {existing.body}"
                existing_combined_emb = self.get_embedding(
                    existing_combined,
                    cache_key=f"combined_{zettel_id}"
                )
                if existing_combined_emb is not None:
                    combined_sim = self.cosine_similarity(new_combined_emb, existing_combined_emb)
                    if combined_sim >= threshold:
                        similarities.append(('combined', combined_sim))
            
            # Add to results if similar enough
            if similarities:
                # Use the highest similarity score
                best_type, best_score = max(similarities, key=lambda x: x[1])
                results.append(SimilarityResult(
                    source_id=new_zettel.id,
                    target_id=zettel_id,
                    similarity_score=best_score,
                    target_title=existing.title,
                    target_tags=existing.tags,
                    similarity_type=best_type
                ))
        
        # Sort by similarity score and limit results
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:max_results]
    
    def _fallback_duplicate_detection(
        self,
        new_zettel: Zettel,
        existing_zettels: Dict[str, Zettel],
        max_results: int = 5
    ) -> List[SimilarityResult]:
        """
        Fallback duplicate detection using simple text matching.
        Used when embeddings are not available.
        """
        results = []
        
        new_title_words = set(new_zettel.title.lower().split())
        new_tags_set = set(new_zettel.tags)
        
        for zettel_id, existing in existing_zettels.items():
            if zettel_id == new_zettel.id:
                continue
            
            # Title word overlap
            existing_title_words = set(existing.title.lower().split())
            title_overlap = len(new_title_words & existing_title_words)
            title_union = len(new_title_words | existing_title_words)
            
            if title_union > 0:
                title_similarity = title_overlap / title_union
                
                # Tag overlap bonus
                tag_overlap = len(new_tags_set & set(existing.tags))
                tag_bonus = tag_overlap * 0.1  # Each shared tag adds 0.1
                
                total_similarity = min(title_similarity + tag_bonus, 1.0)
                
                if total_similarity >= 0.5:  # Lower threshold for fallback
                    results.append(SimilarityResult(
                        source_id=new_zettel.id,
                        target_id=zettel_id,
                        similarity_score=total_similarity,
                        target_title=existing.title,
                        target_tags=existing.tags,
                        similarity_type='fallback'
                    ))
        
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:max_results]
    
    def suggest_tags_semantic(
        self,
        body: str,
        existing_zettels: Dict[str, Zettel],
        max_suggestions: int = 5,
        min_similarity: float = 0.7
    ) -> List[Tuple[str, float]]:
        """
        Suggest tags based on semantic similarity to existing tagged zettels.
        
        Args:
            body: The body text to suggest tags for
            existing_zettels: Dictionary of existing zettels
            max_suggestions: Maximum number of tags to suggest
            min_similarity: Minimum similarity score to consider
        
        Returns:
            List of (tag, confidence_score) tuples
        """
        if not self.is_available():
            return []
        
        # Get embedding for new body
        new_emb = self.get_embedding(body)
        if new_emb is None:
            return []
        
        # Find similar zettels
        similar_zettels = []
        for zettel_id, existing in existing_zettels.items():
            existing_emb = self.get_embedding(
                existing.body,
                cache_key=f"body_{zettel_id}"
            )
            if existing_emb is not None:
                similarity = self.cosine_similarity(new_emb, existing_emb)
                if similarity >= min_similarity:
                    similar_zettels.append((existing, similarity))
        
        # Sort by similarity
        similar_zettels.sort(key=lambda x: x[1], reverse=True)
        
        # Aggregate tags from similar zettels
        tag_scores: Dict[str, float] = {}
        for zettel, similarity in similar_zettels[:10]:  # Use top 10 similar
            for tag in zettel.tags:
                if tag not in tag_scores:
                    tag_scores[tag] = 0
                # Weight by similarity
                tag_scores[tag] += similarity
        
        # Normalize scores
        if tag_scores:
            max_score = max(tag_scores.values())
            tag_scores = {tag: score/max_score for tag, score in tag_scores.items()}
        
        # Sort and return top suggestions
        suggestions = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
        return suggestions[:max_suggestions]
    
    def find_related_by_embedding(
        self,
        zettel: Zettel,
        existing_zettels: Dict[str, Zettel],
        max_results: int = 10,
        min_similarity: float = 0.6
    ) -> List[SimilarityResult]:
        """
        Find related zettels based on semantic similarity.
        Useful for discovering potential relations that weren't explicitly linked.
        
        Args:
            zettel: The zettel to find relations for
            existing_zettels: Dictionary of existing zettels
            max_results: Maximum number of related zettels to return
            min_similarity: Minimum similarity to consider as related
        
        Returns:
            List of related zettels sorted by similarity
        """
        if not self.is_available():
            return []
        
        # Use combined embedding for better context
        combined_text = f"{zettel.title}. {zettel.body}"
        source_emb = self.get_embedding(combined_text)
        if source_emb is None:
            return []
        
        results = []
        
        for zettel_id, existing in existing_zettels.items():
            if zettel_id == zettel.id:
                continue
            
            # Skip if already linked
            existing_relations = set()
            for rel_type, rel_ids in zettel.relations.items():
                existing_relations.update(rel_ids)
            
            if zettel_id in existing_relations:
                continue
            
            # Calculate similarity
            existing_combined = f"{existing.title}. {existing.body}"
            existing_emb = self.get_embedding(
                existing_combined,
                cache_key=f"combined_{zettel_id}"
            )
            
            if existing_emb is not None:
                similarity = self.cosine_similarity(source_emb, existing_emb)
                if similarity >= min_similarity:
                    results.append(SimilarityResult(
                        source_id=zettel.id,
                        target_id=zettel_id,
                        similarity_score=similarity,
                        target_title=existing.title,
                        target_tags=existing.tags,
                        similarity_type='semantic'
                    ))
        
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:max_results]
    
    def clear_cache(self):
        """Clear the embeddings cache to free memory."""
        self.embeddings_cache.clear()
        logger.info("Cleared embeddings cache")


def main():
    """Test semantic analyzer functionality."""
    # Initialize analyzer
    analyzer = SemanticAnalyzer()
    
    if not analyzer.is_available():
        print("Semantic analyzer not available. Please install sentence-transformers.")
        return
    
    # Load existing zettels
    parser = ZettelParser()
    synthetic_dir = Path("synthetic")
    processed_dir = Path("processed")
    
    if synthetic_dir.exists():
        parser.load_from_directory(synthetic_dir)
    if processed_dir.exists():
        parser.load_from_directory(processed_dir, readonly=True)
    
    if not parser.zettels:
        print("No zettels found to analyze.")
        return
    
    # Test duplicate detection on a random zettel
    test_zettel = list(parser.zettels.values())[0]
    print(f"\nTesting duplicate detection for: {test_zettel.title}")
    
    duplicates = analyzer.find_semantic_duplicates(
        test_zettel,
        parser.zettels,
        threshold=0.7
    )
    
    if duplicates:
        print("\nPotential duplicates found:")
        for dup in duplicates:
            print(f"  - {dup.target_title} (ID: {dup.target_id})")
            print(f"    Similarity: {dup.similarity_score:.2%} ({dup.similarity_type})")
            print(f"    Tags: {', '.join(dup.target_tags)}")
    else:
        print("No duplicates found.")
    
    # Test tag suggestions
    print(f"\nTesting tag suggestions for: {test_zettel.title}")
    suggestions = analyzer.suggest_tags_semantic(
        test_zettel.body,
        parser.zettels,
        max_suggestions=3
    )
    
    if suggestions:
        print("\nSuggested tags:")
        for tag, confidence in suggestions:
            print(f"  - {tag}: {confidence:.2%} confidence")
    else:
        print("No tag suggestions available.")
    
    # Test finding related zettels
    print(f"\nFinding related zettels for: {test_zettel.title}")
    related = analyzer.find_related_by_embedding(
        test_zettel,
        parser.zettels,
        max_results=5,
        min_similarity=0.5
    )
    
    if related:
        print("\nRelated zettels (not yet linked):")
        for rel in related:
            print(f"  - {rel.target_title} (ID: {rel.target_id})")
            print(f"    Similarity: {rel.similarity_score:.2%}")
    else:
        print("No related zettels found.")


if __name__ == "__main__":
    main()