"""
Java Search Service for hybrid search, multi-hop retrieval, and reranking.

This service provides semantic and lexical search for Java code, with
multi-hop expansion using call graphs and type hierarchies, and intelligent
reranking based on multiple signals.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from sqlmodel import Session, select
from app.core.config import settings
from app.models.java_chunk import JavaChunk
from app.models.java_repository import JavaRepository
from app.models.code_search_result import CodeSearchResult
from app.services.opensearch_service import opensearch_service
from app.services.java_indexer_service import java_indexer_service
from openai import AsyncOpenAI
import re
import subprocess


class JavaSearchService:
    """
    Service for searching Java code.
    
    Provides hybrid search (semantic + lexical), multi-hop retrieval,
    and reranking with weighted scoring.
    """
    
    def __init__(self):
        """Initialize the Java search service."""
        self.embedding_client = None
        if settings.openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def search_code(
        self,
        session: Session,
        query: str,
        repository_id: Optional[int] = None,
        top_k: int = 10,
        chunk_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Main search entry point - performs hybrid search.
        
        Args:
            session: Database session
            query: Search query text
            repository_id: Optional repository ID to filter by
            top_k: Number of results to return
            chunk_type: Optional chunk type filter (method, class, file, module)
        
        Returns:
            List of search results with scores and metadata
        """
        # Semantic search
        semantic_results = await self._semantic_search(query, repository_id, top_k * 2)
        
        # Lexical search
        lexical_results = await self._lexical_search(
            session, query, repository_id, top_k * 2
        )
        
        # Merge and deduplicate
        merged_results = self._merge_results(semantic_results, lexical_results)
        
        # Rerank
        reranked = await self._rerank_results(session, merged_results, query, top_k)
        
        return reranked
    
    async def _semantic_search(
        self,
        query: str,
        repository_id: Optional[int],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic vector search using OpenSearch.
        
        Args:
            query: Search query
            repository_id: Optional repository filter
            top_k: Number of results
        
        Returns:
            List of search results
        """
        # Check if OpenSearch is enabled and available
        if not settings.java_opensearch_enabled:
            return []
        
        if not opensearch_service.is_available():
            return []
        
        try:
            # Generate query embedding
            if not self.embedding_client:
                return []
            
            embedding_response = await self.embedding_client.embeddings.create(
                model=settings.java_embedding_model,
                input=[query]
            )
            query_embedding = embedding_response.data[0].embedding
            
            # Build search query
            search_body = {
                "size": top_k,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": query_embedding,
                            "k": top_k
                        }
                    }
                },
                "_source": ["chunk_id", "repository_id", "type", "fqn", "file_path", "code", "summary"]
            }
            
            # Add repository filter if specified
            if repository_id:
                search_body["query"] = {
                    "bool": {
                        "must": [
                            {
                                "knn": {
                                    "embedding": {
                                        "vector": query_embedding,
                                        "k": top_k
                                    }
                                }
                            }
                        ],
                        "filter": [
                            {"term": {"repository_id": repository_id}}
                        ]
                    }
                }
            
            # Ensure index exists before searching
            await opensearch_service.ensure_java_index_exists()
            
            # Search OpenSearch
            try:
                response = opensearch_service.client.search(
                    index=settings.java_opensearch_index,
                    body=search_body
                )
                
                results = []
                for hit in response.get('hits', {}).get('hits', []):
                    source = hit.get('_source', {})
                    results.append({
                        'chunk_id': source.get('chunk_id'),
                        'repository_id': source.get('repository_id'),
                        'type': source.get('type'),
                        'fqn': source.get('fqn'),
                        'file_path': source.get('file_path'),
                        'code': source.get('code'),
                        'summary': source.get('summary'),
                        'semantic_score': hit.get('_score', 0.0),
                        'lexical_score': 0.0,
                        'graph_proximity': 0.0,
                        'runtime_hits': 0.0
                    })
                
                return results
            except Exception as e:
                print(f"⚠️ Error searching OpenSearch: {e}")
                return []
            
        except Exception as e:
            print(f"❌ Error in semantic search: {e}")
            return []
    
    async def _lexical_search(
        self,
        session: Session,
        query: str,
        repository_id: Optional[int],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Perform lexical search using database queries and file system search.
        
        Args:
            session: Database session
            query: Search query
            repository_id: Optional repository filter
            top_k: Number of results
        
        Returns:
            List of search results
        """
        results = []
        
        try:
            # Search in database by FQN, summary, or code content
            statement = select(JavaChunk)
            
            if repository_id:
                statement = statement.where(JavaChunk.repository_id == repository_id)
            
            # Search in FQN and summary
            query_lower = query.lower()
            all_chunks = session.exec(statement).all()
            
            for chunk in all_chunks:
                score = 0.0
                
                # Check FQN match
                if query_lower in chunk.fqn.lower():
                    score += 2.0
                
                # Check summary match
                if chunk.summary and query_lower in chunk.summary.lower():
                    score += 1.5
                
                # Check code content match
                if query_lower in chunk.code.lower():
                    score += 1.0
                
                if score > 0:
                    results.append({
                        'chunk_id': chunk.id,
                        'repository_id': chunk.repository_id,
                        'type': chunk.type,
                        'fqn': chunk.fqn,
                        'file_path': chunk.file_path,
                        'code': chunk.code,
                        'summary': chunk.summary,
                        'semantic_score': 0.0,
                        'lexical_score': score,
                        'graph_proximity': 0.0,
                        'runtime_hits': 0.0
                    })
            
            # Sort by lexical score and take top K
            results.sort(key=lambda x: x['lexical_score'], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            print(f"❌ Error in lexical search: {e}")
            return []
    
    def _merge_results(
        self,
        semantic_results: List[Dict[str, Any]],
        lexical_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge semantic and lexical results with deduplication.
        
        Args:
            semantic_results: Results from semantic search
            lexical_results: Results from lexical search
        
        Returns:
            Merged and deduplicated results
        """
        # Create map by chunk_id
        merged_map = {}
        
        # Add semantic results
        for result in semantic_results:
            chunk_id = result.get('chunk_id')
            if chunk_id:
                merged_map[chunk_id] = result
        
        # Merge lexical results
        for result in lexical_results:
            chunk_id = result.get('chunk_id')
            if chunk_id in merged_map:
                # Update existing result with lexical score
                merged_map[chunk_id]['lexical_score'] = max(
                    merged_map[chunk_id].get('lexical_score', 0.0),
                    result.get('lexical_score', 0.0)
                )
            else:
                merged_map[chunk_id] = result
        
        return list(merged_map.values())
    
    async def _rerank_results(
        self,
        session: Session,
        results: List[Dict[str, Any]],
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using weighted scoring.
        
        Scoring formula:
        - 45% semantic similarity
        - 25% lexical match
        - 15% graph proximity
        - 10% test references
        - 5% runtime matches (placeholder)
        
        Args:
            session: Database session
            results: List of search results
            query: Original query
            top_k: Number of results to return
        
        Returns:
            Reranked results with confidence scores
        """
        # Calculate graph proximity and test references
        for result in results:
            chunk_id = result.get('chunk_id')
            if not chunk_id:
                continue
            
            chunk = session.get(JavaChunk, chunk_id)
            if not chunk:
                continue
            
            # Calculate graph proximity (simplified - based on callers/callees)
            callers = chunk.get_callers()
            callees = chunk.get_callees()
            graph_proximity = (len(callers) + len(callees)) * 0.1  # Normalize
            result['graph_proximity'] = min(graph_proximity, 1.0)
            
            # Check test references
            test_refs = chunk.get_test_references()
            test_score = min(len(test_refs) * 0.2, 1.0) if test_refs else 0.0
            result['test_references'] = test_score
        
        # Normalize scores
        max_semantic = max([r.get('semantic_score', 0.0) for r in results], default=1.0)
        max_lexical = max([r.get('lexical_score', 0.0) for r in results], default=1.0)
        
        for result in results:
            # Normalize scores to 0-1 range
            semantic_norm = (result.get('semantic_score', 0.0) / max_semantic) if max_semantic > 0 else 0.0
            lexical_norm = (result.get('lexical_score', 0.0) / max_lexical) if max_lexical > 0 else 0.0
            
            # Calculate weighted score
            final_score = (
                0.45 * semantic_norm +
                0.25 * lexical_norm +
                0.15 * result.get('graph_proximity', 0.0) +
                0.10 * result.get('test_references', 0.0) +
                0.05 * result.get('runtime_hits', 0.0)
            )
            
            result['confidence'] = final_score
            result['final_score'] = final_score
        
        # Sort by final score
        results.sort(key=lambda x: x.get('final_score', 0.0), reverse=True)
        
        return results[:top_k]
    
    async def expand_by_callers(
        self,
        session: Session,
        chunk_id: int,
        max_depth: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Expand search results by finding callers of a method.
        
        Args:
            session: Database session
            chunk_id: Chunk ID to expand from
            max_depth: Maximum depth for expansion
        
        Returns:
            List of expanded chunks
        """
        chunk = session.get(JavaChunk, chunk_id)
        if not chunk or chunk.type != "method":
            return []
        
        callers = chunk.get_callers()
        if not callers:
            return []
        
        # Find caller chunks
        expanded = []
        for caller_fqn in callers[:10]:  # Limit to 10 callers
            caller_chunk = session.exec(
                select(JavaChunk).where(
                    JavaChunk.fqn == caller_fqn,
                    JavaChunk.repository_id == chunk.repository_id
                )
            ).first()
            
            if caller_chunk:
                expanded.append({
                    'chunk_id': caller_chunk.id,
                    'fqn': caller_chunk.fqn,
                    'file_path': caller_chunk.file_path,
                    'code': caller_chunk.code,
                    'summary': caller_chunk.summary,
                    'relationship': 'caller'
                })
        
        return expanded
    
    async def expand_by_callees(
        self,
        session: Session,
        chunk_id: int,
        max_depth: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Expand search results by finding callees of a method.
        
        Args:
            session: Database session
            chunk_id: Chunk ID to expand from
            max_depth: Maximum depth for expansion
        
        Returns:
            List of expanded chunks
        """
        chunk = session.get(JavaChunk, chunk_id)
        if not chunk or chunk.type != "method":
            return []
        
        callees = chunk.get_callees()
        if not callees:
            return []
        
        # Find callee chunks
        expanded = []
        for callee_fqn in callees[:10]:  # Limit to 10 callees
            callee_chunk = session.exec(
                select(JavaChunk).where(
                    JavaChunk.fqn == callee_fqn,
                    JavaChunk.repository_id == chunk.repository_id
                )
            ).first()
            
            if callee_chunk:
                expanded.append({
                    'chunk_id': callee_chunk.id,
                    'fqn': callee_chunk.fqn,
                    'file_path': callee_chunk.file_path,
                    'code': callee_chunk.code,
                    'summary': callee_chunk.summary,
                    'relationship': 'callee'
                })
        
        return expanded
    
    async def expand_by_type_hierarchy(
        self,
        session: Session,
        chunk_id: int
    ) -> List[Dict[str, Any]]:
        """
        Expand search results by finding related classes in type hierarchy.
        
        Args:
            session: Database session
            chunk_id: Chunk ID to expand from
        
        Returns:
            List of expanded chunks
        """
        chunk = session.get(JavaChunk, chunk_id)
        if not chunk or chunk.type != "class":
            return []
        
        expanded = []
        
        # Find extended class
        if chunk.extended_class:
            parent_chunk = session.exec(
                select(JavaChunk).where(
                    JavaChunk.fqn == chunk.extended_class,
                    JavaChunk.repository_id == chunk.repository_id,
                    JavaChunk.type == "class"
                )
            ).first()
            
            if parent_chunk:
                expanded.append({
                    'chunk_id': parent_chunk.id,
                    'fqn': parent_chunk.fqn,
                    'file_path': parent_chunk.file_path,
                    'code': parent_chunk.code,
                    'summary': parent_chunk.summary,
                    'relationship': 'parent_class'
                })
        
        # Find implemented interfaces
        interfaces = chunk.get_implemented_interfaces()
        for interface_fqn in interfaces[:5]:  # Limit to 5 interfaces
            interface_chunk = session.exec(
                select(JavaChunk).where(
                    JavaChunk.fqn == interface_fqn,
                    JavaChunk.repository_id == chunk.repository_id,
                    JavaChunk.type == "class"
                )
            ).first()
            
            if interface_chunk:
                expanded.append({
                    'chunk_id': interface_chunk.id,
                    'fqn': interface_chunk.fqn,
                    'file_path': interface_chunk.file_path,
                    'code': interface_chunk.code,
                    'summary': interface_chunk.summary,
                    'relationship': 'interface'
                })
        
        return expanded


# Global instance
java_search_service = JavaSearchService()

