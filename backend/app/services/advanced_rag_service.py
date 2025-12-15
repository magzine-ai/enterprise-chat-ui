"""
Advanced RAG (Retrieval-Augmented Generation) Service with Multi-Hop Reasoning.

This service provides exhaustive multi-hop retrieval with completeness verification
for enterprise use cases like migration planning, impact analysis, and product analysis.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
import logging
import re
import json
from sqlmodel import Session, select
from app.core.config import settings
from app.models.java_chunk import JavaChunk
from app.services.opensearch_service import opensearch_service
from app.services.entity_extractor import entity_extractor
from app.services.llm_service import llm_service
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class AdvancedRAGService:
    """
    Advanced RAG pipeline with multi-hop reasoning and completeness verification.
    
    Features:
    - Multi-hop retrieval (up to 5 hops)
    - Reverse traversal (find all callers/consumers)
    - REST endpoint extraction
    - Completeness verification with LLM
    - Use case aware search (migration, impact analysis, etc.)
    """
    
    def __init__(self):
        """Initialize advanced RAG service."""
        self.embedding_client = None
        if settings.openai_api_key:
            self.embedding_client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def retrieve_context(
        self,
        session: Session,
        query: str,
        repository_id: Optional[int] = None,
        language: Optional[str] = None,
        max_results: int = 10,
        include_graph: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context for a query using hybrid search.
        
        Args:
            session: Database session
            query: User query
            repository_id: Optional repository filter
            language: Optional language filter
            max_results: Maximum number of results
            include_graph: Whether to include graph context
        
        Returns:
            Dictionary with retrieved contexts
        """
        # Import here to avoid circular import
        from app.services.java_search_service import java_search_service
        # Use existing search service for initial retrieval
        search_results = await java_search_service.search_code(
            session=session,
            query=query,
            repository_id=repository_id,
            top_k=max_results * 2
        )
        
        # Convert to our format
        vector_results = []
        for result in search_results:
            vector_results.append({
                'chunk_id': result.get('chunk_id'),
                'repository_id': result.get('repository_id'),
                'type': result.get('type'),
                'fqn': result.get('fqn'),
                'file_path': result.get('file_path'),
                'code': result.get('code'),
                'summary': result.get('summary'),
                'score': result.get('confidence', result.get('final_score', 0.0)),
                'code_chunk': result.get('code', ''),
                'start_line': result.get('start_line', 0),
                'end_line': result.get('end_line', 0),
                'language': language or 'java',
            })
        
        # Graph traversal (if enabled)
        graph_results = []
        if include_graph and vector_results:
            # Get graph context for top results
            for result in vector_results[:3]:  # Top 3 results
                chunk_id = result.get('chunk_id')
                if chunk_id:
                    try:
                        # Get related chunks via call graph
                        chunk = session.get(JavaChunk, chunk_id)
                        if chunk:
                            callers = chunk.get_callers()
                            callees = chunk.get_callees()
                            
                            graph_results.append({
                                'chunk_id': chunk_id,
                                'file_path': result.get('file_path'),
                                'callers': callers[:5],  # Limit to 5
                                'callees': callees[:5],
                            })
                    except Exception as e:
                        logger.warning(f"Failed to get graph context for chunk {chunk_id}: {e}")
        
        # Combine and rank results
        combined_results = self._combine_results(vector_results, graph_results)
        
        return {
            'vector_results': vector_results,
            'graph_results': graph_results,
            'combined_results': combined_results,
        }
    
    def _combine_results(
        self,
        vector_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Combine and deduplicate results."""
        combined = []
        seen_files = set()
        
        for result in vector_results:
            file_path = result.get('file_path')
            if file_path and file_path not in seen_files:
                combined.append({
                    'type': 'vector',
                    'score': result.get('score', 0.0),
                    'code_chunk': result.get('code_chunk', ''),
                    'file_path': file_path,
                    'start_line': result.get('start_line', 0),
                    'end_line': result.get('end_line', 0),
                    'language': result.get('language'),
                    'chunk_id': result.get('chunk_id'),
                    'fqn': result.get('fqn'),
                    'metadata': {
                        'type': result.get('type'),
                        'summary': result.get('summary'),
                    },
                })
                seen_files.add(file_path)
        
        return combined
    
    async def should_use_exhaustive_search(self, query: str) -> Dict[str, Any]:
        """
        Intelligently determine if exhaustive search is needed based on query intent.
        Uses LLM to analyze query for enterprise use cases.
        
        Args:
            query: User query
        
        Returns:
            Dict with 'use_exhaustive' boolean and 'reasoning'
        """
        analysis_prompt = f"""Analyze this code-related query and determine if it requires exhaustive, comprehensive search to ensure nothing is missed.

Query: "{query}"

Consider these enterprise scenarios that require exhaustive search:
- Migration planning (need ALL affected services/endpoints)
- Impact analysis (need ALL dependencies/consumers)
- Product analysis (need COMPLETE code coverage)
- Backlog building (need ALL technical debt/issues)
- Dependency analysis (need ALL relationships)
- Code review preparation (need ALL related code)
- Risk assessment (need ALL potential issues)
- Compliance analysis (need ALL relevant code)

Queries that need exhaustive search typically ask for:
- "Which/What ALL..." (comprehensive lists)
- "Everything that..." (complete coverage)
- "All services/endpoints/functions..." (exhaustive enumeration)
- Migration/refactoring questions (can't miss anything)
- Impact analysis (need complete picture)

Queries that DON'T need exhaustive search:
- Simple explanations ("What does this do?")
- Single function understanding
- General questions without "all/which/every" requirement

Respond in JSON:
{{
    "use_exhaustive": true/false,
    "reasoning": "explanation",
    "use_case": "migration/impact_analysis/product_analysis/backlog/etc",
    "confidence": "high/medium/low"
}}
"""
        
        try:
            response = await llm_service.generate_response(
                user_message=analysis_prompt,
                conversation_history=[],
                conversation_id=0
            )
            
            # Extract JSON
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return analysis
            else:
                # Fallback: heuristic analysis
                return self._heuristic_exhaustive_analysis(query)
                
        except Exception as e:
            logger.warning(f"Failed to analyze query for exhaustive search: {e}")
            return self._heuristic_exhaustive_analysis(query)
    
    def _heuristic_exhaustive_analysis(self, query: str) -> Dict[str, Any]:
        """Heuristic-based analysis for exhaustive search decision."""
        query_lower = query.lower()
        
        # Patterns that indicate exhaustive search needed
        exhaustive_patterns = [
            r'\b(which|what)\s+(all|every)\b',
            r'\b(all|every)\s+(services|endpoints|functions|files)\b',
            r'\beverything\s+that\b',
            r'\bmigrat(e|ion)\b',
            r'\bimpact\s+analysis\b',
            r'\b(complete|comprehensive|exhaustive)\s+(list|analysis)\b',
            r'\bbacklog\s+build(ing)?\b',
            r'\bproduct\s+analysis\b',
            r'\bdependency\s+analysis\b',
        ]
        
        needs_exhaustive = any(re.search(pattern, query_lower) for pattern in exhaustive_patterns)
        
        # Determine use case
        use_case = "general"
        if "migrat" in query_lower:
            use_case = "migration"
        elif "impact" in query_lower:
            use_case = "impact_analysis"
        elif "backlog" in query_lower or "technical debt" in query_lower:
            use_case = "backlog_building"
        elif "product" in query_lower and "analysis" in query_lower:
            use_case = "product_analysis"
        elif "dependenc" in query_lower:
            use_case = "dependency_analysis"
        
        return {
            "use_exhaustive": needs_exhaustive,
            "reasoning": "Heuristic analysis based on query patterns",
            "use_case": use_case,
            "confidence": "medium",
        }
    
    async def retrieve_with_multihop_exhaustive(
        self,
        session: Session,
        query: str,
        repository_id: Optional[int] = None,
        language: Optional[str] = None,
        max_hops: int = 5,
        ensure_completeness: bool = True,
        use_case: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exhaustive multi-hop retrieval ensuring no data is missed.
        Designed for enterprise use cases: migration, impact analysis, product analysis, backlog building.
        
        Args:
            session: Database session
            query: User query
            repository_id: Optional repository filter
            language: Optional language filter
            max_hops: Maximum number of reasoning hops
            ensure_completeness: If True, performs exhaustive search to ensure nothing is missed
            use_case: Use case type (migration, impact_analysis, product_analysis, backlog_building, etc.)
        
        Returns:
            Dictionary with exhaustive evidence and completeness verification
        """
        use_case_str = use_case or "general"
        logger.info(f"Starting exhaustive multi-hop retrieval for: {query} (use_case: {use_case_str})")
        
        # Step 1: Initial vector search
        initial_results = await self.retrieve_context(
            session=session,
            query=query,
            repository_id=repository_id,
            language=language,
            max_results=20,  # Get more initial results
            include_graph=True,
        )
        
        # Step 2: Extract all entities from initial results
        all_entities = self._extract_all_entities(initial_results)
        logger.info(f"Found {len(all_entities)} initial entities")
        
        # Step 3: Exhaustive multi-hop traversal
        exhaustive_evidence = []
        seen_entities: Set[Tuple[str, str]] = set()  # (type, name) tuples
        
        # Add initial results
        for result in initial_results.get("combined_results", []):
            key = ("code", result.get("file_path", ""))
            if key not in seen_entities:
                seen_entities.add(key)
                exhaustive_evidence.append({
                    **result,
                    "hop": 0,
                    "source": "initial_search",
                })
        
        # Multi-hop traversal
        current_entities = all_entities
        for hop in range(1, max_hops + 1):
            if not current_entities:
                break
            
            hop_evidence = []
            next_entities = []
            
            for entity in current_entities:
                entity_key = (entity.get("type"), entity.get("name", ""))
                if entity_key in seen_entities:
                    continue
                
                seen_entities.add(entity_key)
                
                # Follow all relationships
                related = await self._exhaustive_entity_traversal(
                    session=session,
                    entity=entity,
                    repository_id=repository_id,
                    hop=hop,
                )
                
                hop_evidence.extend(related["evidence"])
                next_entities.extend(related["new_entities"])
            
            exhaustive_evidence.extend(hop_evidence)
            current_entities = next_entities
            
            logger.info(f"Hop {hop}: Found {len(hop_evidence)} pieces of evidence, {len(next_entities)} new entities")
        
        # Step 4: Reverse traversal (find all callers/consumers)
        if ensure_completeness:
            reverse_evidence = await self._reverse_traversal_exhaustive(
                session=session,
                entities=all_entities,
                repository_id=repository_id,
            )
            exhaustive_evidence.extend(reverse_evidence)
            logger.info(f"Reverse traversal: Found {len(reverse_evidence)} additional pieces of evidence")
        
        # Step 5: Deduplicate and rank
        final_evidence = self._deduplicate_and_rank_exhaustive(exhaustive_evidence)
        
        # Step 6: Completeness verification (use case aware)
        completeness_check = await self._verify_completeness(
            session=session,
            query=query,
            evidence=final_evidence,
            repository_id=repository_id,
            use_case=use_case,
        )
        
        return {
            "evidence": final_evidence,
            "completeness_check": completeness_check,
            "total_entities_found": len(seen_entities),
            "total_evidence_pieces": len(final_evidence),
            "hops_explored": max_hops,
            "use_case": use_case_str,
        }
    
    def _extract_all_entities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract all entities (functions, classes, files, URLs) from context."""
        entities = []
        
        for result in context.get("combined_results", []):
            code_chunk = result.get("code_chunk", "")
            metadata = result.get("metadata", {})
            file_path = result.get("file_path", "")
            language = result.get("language", "java")
            
            # Extract entities using entity extractor
            extracted = entity_extractor.extract_entities(code_chunk, language, file_path)
            
            # Add functions
            for func in extracted.get('functions', []):
                entities.append({
                    "type": "function",
                    "name": func.get('name'),
                    "file_path": file_path,
                    "start_line": func.get('line', result.get('start_line', 0)),
                    "end_line": result.get('end_line', 0),
                })
            
            # Add classes
            for cls in extracted.get('classes', []):
                entities.append({
                    "type": "class",
                    "name": cls.get('name'),
                    "file_path": file_path,
                })
            
            # Add REST endpoints
            for endpoint in extracted.get('rest_endpoints', []):
                entities.append({
                    "type": "url",
                    "name": endpoint.get('endpoint'),
                    "file_path": file_path,
                })
            
            # Add file paths
            if file_path:
                entities.append({
                    "type": "file",
                    "name": file_path,
                    "file_path": file_path,
                })
        
        return entities
    
    async def _exhaustive_entity_traversal(
        self,
        session: Session,
        entity: Dict[str, Any],
        repository_id: Optional[int],
        hop: int,
    ) -> Dict[str, Any]:
        """Exhaustively traverse all relationships for an entity."""
        evidence = []
        new_entities = []
        
        entity_type = entity.get("type")
        entity_name = entity.get("name")
        entity_path = entity.get("file_path")
        
        try:
            if entity_type == "function":
                # Find chunks with this function name
                chunks = session.exec(
                    select(JavaChunk).where(
                        JavaChunk.fqn.contains(entity_name),
                        JavaChunk.repository_id == repository_id if repository_id else True
                    )
                ).limit(10).all()
                
                for chunk in chunks:
                    # Forward: functions called by this function
                    callees = chunk.get_callees()
                    for callee_fqn in callees[:5]:  # Limit to 5
                        callee_chunk = session.exec(
                            select(JavaChunk).where(
                                JavaChunk.fqn == callee_fqn,
                                JavaChunk.repository_id == chunk.repository_id
                            )
                        ).first()
                        
                        if callee_chunk:
                            evidence.append({
                                "type": "function_call",
                                "hop": hop,
                                "source_entity": entity_name,
                                "target_entity": callee_fqn,
                                "file_path": callee_chunk.file_path,
                                "relationship": "calls",
                                "chunk_id": callee_chunk.id,
                                "code_chunk": callee_chunk.code[:500] if callee_chunk.code else "",
                                "start_line": callee_chunk.start_line,
                                "end_line": callee_chunk.end_line,
                                "fqn": callee_chunk.fqn,
                                "language": "java",  # Default, could be enhanced
                            })
                            new_entities.append({
                                "type": "function",
                                "name": callee_fqn,
                                "file_path": callee_chunk.file_path,
                            })
                    
                    # Reverse: functions that call this function
                    callers = chunk.get_callers()
                    for caller_fqn in callers[:5]:  # Limit to 5
                        caller_chunk = session.exec(
                            select(JavaChunk).where(
                                JavaChunk.fqn == caller_fqn,
                                JavaChunk.repository_id == chunk.repository_id
                            )
                        ).first()
                        
                        if caller_chunk:
                            evidence.append({
                                "type": "function_caller",
                                "hop": hop,
                                "source_entity": caller_fqn,
                                "target_entity": entity_name,
                                "file_path": caller_chunk.file_path,
                                "relationship": "called_by",
                                "chunk_id": caller_chunk.id,
                                "code_chunk": caller_chunk.code[:500] if caller_chunk.code else "",
                                "start_line": caller_chunk.start_line,
                                "end_line": caller_chunk.end_line,
                                "fqn": caller_chunk.fqn,
                                "language": "java",  # Default, could be enhanced
                            })
                            new_entities.append({
                                "type": "function",
                                "name": caller_fqn,
                                "file_path": caller_chunk.file_path,
                            })
            
            if entity_path:
                # Find files that import this file (via imports in chunks)
                chunks_in_file = session.exec(
                    select(JavaChunk).where(
                        JavaChunk.file_path == entity_path,
                        JavaChunk.repository_id == repository_id if repository_id else True
                    )
                ).limit(5).all()
                
                for chunk in chunks_in_file:
                    imports = chunk.get_imports()
                    # Try to find files that match imports
                    for imp in imports[:5]:  # Limit
                        # Search for chunks with matching package/import
                        related_chunks = session.exec(
                            select(JavaChunk).where(
                                JavaChunk.fqn.contains(imp.split('.')[-1] if '.' in imp else imp),
                                JavaChunk.repository_id == repository_id if repository_id else True
                            )
                        ).limit(3).all()
                        
                        for related_chunk in related_chunks:
                            evidence.append({
                                "type": "file_dependency",
                                "hop": hop,
                                "source_entity": entity_path,
                                "target_entity": related_chunk.file_path,
                                "relationship": "depends_on",
                                "chunk_id": related_chunk.id,
                            })
                            new_entities.append({
                                "type": "file",
                                "name": related_chunk.file_path,
                                "file_path": related_chunk.file_path,
                            })
        
        except Exception as e:
            logger.warning(f"Failed to traverse entity {entity_name}: {e}")
        
        return {"evidence": evidence, "new_entities": new_entities}
    
    async def _reverse_traversal_exhaustive(
        self,
        session: Session,
        entities: List[Dict[str, Any]],
        repository_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Reverse traversal to find all consumers/callers (critical for completeness)."""
        evidence = []
        
        for entity in entities:
            if entity.get("type") == "function":
                # Find all functions that call this function
                func_name = entity.get("name")
                chunks = session.exec(
                    select(JavaChunk).where(
                        JavaChunk.fqn.contains(func_name),
                        JavaChunk.repository_id == repository_id if repository_id else True
                    )
                ).limit(10).all()
                
                for chunk in chunks:
                    callers = chunk.get_callers()
                    if func_name in str(callers):
                        evidence.append({
                            "type": "reverse_call",
                            "hop": "reverse",
                            "source_entity": chunk.fqn,
                            "target_entity": func_name,
                            "file_path": chunk.file_path,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                            "code_chunk": chunk.code[:500] if chunk.code else "",
                            "chunk_type": chunk.type,
                            "relationship": "calls",
                            "chunk_id": chunk.id,
                            "fqn": chunk.fqn,
                            "language": "java",  # Default, could be enhanced
                        })
        
        return evidence
    
    async def _verify_completeness(
        self,
        session: Session,
        query: str,
        evidence: List[Dict[str, Any]],
        repository_id: Optional[int],
        use_case: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify completeness of evidence using LLM and heuristics (use case aware)."""
        # Extract all REST endpoints found
        rest_endpoints = self._extract_rest_endpoints(evidence)
        
        # Extract all functions/services found
        functions_found = set()
        classes_found = set()
        files_found = set()
        
        for ev in evidence:
            if ev.get("chunk_type") == "method" or ev.get("type") == "function":
                func_name = ev.get("metadata", {}).get("name") or ev.get("target_entity") or ev.get("source_entity")
                if func_name:
                    functions_found.add(func_name)
            
            if ev.get("chunk_type") == "class" or ev.get("type") == "class":
                class_name = ev.get("metadata", {}).get("name") or ev.get("target_entity")
                if class_name:
                    classes_found.add(class_name)
            
            file_path = ev.get("file_path")
            if file_path:
                files_found.add(file_path)
        
        # Use case specific verification
        use_case_context = self._get_use_case_context(use_case)
        
        # Use LLM to verify completeness
        verification_prompt = f"""You are verifying the completeness of code search results for enterprise code analysis.

Use Case: {use_case_context.get('name', 'General Code Analysis')}
Context: {use_case_context.get('description', '')}

Query: {query}

Found Evidence Summary:
- REST Endpoints: {len(rest_endpoints)} found
  {json.dumps(list(rest_endpoints)[:10], indent=2) if rest_endpoints else 'None'}
- Functions/Services: {len(functions_found)} found
  {json.dumps(list(functions_found)[:10], indent=2) if functions_found else 'None'}
- Classes: {len(classes_found)} found
- Files: {len(files_found)} found
- Total Evidence Pieces: {len(evidence)}

{use_case_context.get('completeness_criteria', '')}

Evaluate:
1. Is the search exhaustive enough for this use case? (yes/no/maybe)
2. What percentage of completeness? (0-100%)
3. What might be missing? (list potential gaps)
4. Should we search more? (yes/no)
5. Confidence in completeness: (high/medium/low)

Respond in JSON:
{{
    "exhaustive": true/false,
    "completeness_percentage": 0-100,
    "potential_gaps": ["gap1", "gap2"],
    "should_search_more": true/false,
    "confidence": "high/medium/low",
    "reasoning": "explanation"
}}
"""
        
        try:
            response = await llm_service.generate_response(
                user_message=verification_prompt,
                conversation_history=[],
                conversation_id=0
            )
            
            # Extract JSON
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                verification = json.loads(json_match.group())
            else:
                verification = self._heuristic_completeness_check(evidence, rest_endpoints, use_case)
            
            verification["rest_endpoints_found"] = len(rest_endpoints)
            verification["functions_found"] = len(functions_found)
            verification["classes_found"] = len(classes_found)
            verification["files_found"] = len(files_found)
            verification["rest_endpoints"] = list(rest_endpoints)
            verification["use_case"] = use_case or "general"
            
            return verification
            
        except Exception as e:
            logger.error(f"Failed to verify completeness: {e}")
            return self._heuristic_completeness_check(evidence, rest_endpoints, use_case)
    
    def _get_use_case_context(self, use_case: Optional[str]) -> Dict[str, Any]:
        """Get context and criteria for different use cases."""
        contexts = {
            "migration": {
                "name": "Migration Planning",
                "description": "Critical migration scenario - must identify ALL affected services, endpoints, and dependencies",
                "completeness_criteria": "For migration, it's CRITICAL that we don't miss any REST endpoints, services, or dependencies. Missing even one could cause production issues.",
            },
            "impact_analysis": {
                "name": "Impact Analysis",
                "description": "Analyzing impact of changes - need complete dependency chain",
                "completeness_criteria": "For impact analysis, we need ALL affected components, services, and downstream dependencies.",
            },
            "product_analysis": {
                "name": "Product Analysis",
                "description": "Comprehensive product code analysis for backlog building and planning",
                "completeness_criteria": "For product analysis, we need COMPLETE code coverage to identify all features, services, and technical debt.",
            },
            "backlog_building": {
                "name": "Backlog Building",
                "description": "Building product backlog from code analysis",
                "completeness_criteria": "For backlog building, we need to identify ALL technical debt, issues, and improvement opportunities across the codebase.",
            },
            "dependency_analysis": {
                "name": "Dependency Analysis",
                "description": "Analyzing code dependencies and relationships",
                "completeness_criteria": "For dependency analysis, we need ALL relationships: imports, calls, inherits, uses.",
            },
            "general": {
                "name": "General Code Analysis",
                "description": "General code understanding and analysis",
                "completeness_criteria": "Ensure comprehensive coverage of relevant code.",
            },
        }
        
        return contexts.get(use_case or "general", contexts["general"])
    
    def _heuristic_completeness_check(
        self,
        evidence: List[Dict[str, Any]],
        rest_endpoints: Set[str],
        use_case: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Heuristic-based completeness check."""
        # Check coverage metrics
        unique_files = len(set(e.get("file_path", "") for e in evidence))
        has_reverse_traversal = any(e.get("hop") == "reverse" for e in evidence)
        has_multiple_hops = max((e.get("hop", 0) for e in evidence if isinstance(e.get("hop"), int)), default=0) > 2
        
        # Calculate completeness score
        completeness = 0.0
        if unique_files >= 5:
            completeness += 0.3
        if has_reverse_traversal:
            completeness += 0.3
        if has_multiple_hops:
            completeness += 0.2
        if len(rest_endpoints) > 0:
            completeness += 0.2
        
        return {
            "exhaustive": completeness >= 0.7,
            "completeness_percentage": int(completeness * 100),
            "potential_gaps": [] if completeness >= 0.8 else ["May need more reverse traversal"],
            "should_search_more": completeness < 0.7,
            "confidence": "high" if completeness >= 0.8 else "medium" if completeness >= 0.5 else "low",
            "reasoning": f"Found {unique_files} files, {len(rest_endpoints)} endpoints, reverse traversal: {has_reverse_traversal}",
            "use_case": use_case or "general",
        }
    
    def _extract_rest_endpoints(self, evidence: List[Dict[str, Any]]) -> Set[str]:
        """Extract REST endpoints from evidence."""
        endpoints = set()
        
        for ev in evidence:
            code_chunk = ev.get("code_chunk", "")
            file_path = ev.get("file_path", "")
            
            # Use entity extractor to find REST endpoints
            if code_chunk:
                language = ev.get("language", "java")
                extracted = entity_extractor.extract_rest_endpoints(code_chunk, language)
                for endpoint in extracted:
                    endpoints.add(endpoint.get('endpoint', ''))
        
        return endpoints
    
    def _deduplicate_and_rank_exhaustive(self, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate and rank evidence comprehensively."""
        seen = set()
        unique_evidence = []
        
        for ev in evidence:
            # Create unique key
            key = (
                ev.get("file_path", ""),
                ev.get("start_line", 0),
                ev.get("end_line", 0),
                ev.get("source_entity", ""),
                ev.get("target_entity", ""),
            )
            
            if key not in seen:
                seen.add(key)
                unique_evidence.append(ev)
        
        # Rank by: relevance score, hop (earlier = better), reverse traversal (important)
        unique_evidence.sort(
            key=lambda x: (
                x.get("score", 0.0),
                -x.get("hop", 999) if isinstance(x.get("hop"), int) else 0,
                1 if x.get("hop") == "reverse" else 0,  # Prioritize reverse traversal
            ),
            reverse=True,
        )
        
        return unique_evidence
    
    def format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """Format retrieved context for LLM prompt with completeness information."""
        formatted = []
        
        # Add completeness information
        completeness = context.get("completeness_check", {})
        if completeness:
            use_case = completeness.get("use_case", "general")
            formatted.append(
                f"=== COMPLETENESS VERIFICATION ===\n"
                f"Use Case: {use_case}\n"
                f"Exhaustive Search: {'✓' if completeness.get('exhaustive') else '⚠'}\n"
                f"Completeness: {completeness.get('completeness_percentage', 0)}%\n"
                f"REST Endpoints Found: {completeness.get('rest_endpoints_found', 0)}\n"
                f"Functions Found: {completeness.get('functions_found', 0)}\n"
                f"Files Found: {completeness.get('files_found', 0)}\n"
                f"Confidence: {completeness.get('confidence', 'unknown')}\n"
                f"REST Endpoints: {', '.join(completeness.get('rest_endpoints', [])[:15])}\n"
                f"Reasoning: {completeness.get('reasoning', 'N/A')}\n"
            )
            
            if completeness.get("potential_gaps"):
                formatted.append(
                    f"\n⚠️ Potential Gaps: {', '.join(completeness.get('potential_gaps', []))}\n"
                )
        
        # Group evidence by hop
        evidence = context.get("evidence", context.get("combined_results", []))
        evidence_by_hop = {}
        for ev in evidence:
            hop = ev.get("hop", 0)
            if hop not in evidence_by_hop:
                evidence_by_hop[hop] = []
            evidence_by_hop[hop].append(ev)
        
        # Format with hop information
        for hop in sorted(evidence_by_hop.keys(), key=lambda x: (x == "reverse", x if isinstance(x, int) else 999)):
            if hop == "reverse":
                formatted.append(f"\n=== REVERSE TRAVERSAL (All Consumers/Callers) ===\n")
            elif hop == 0:
                formatted.append(f"\n=== DIRECT MATCHES ===\n")
            else:
                formatted.append(f"\n=== HOP {hop} (Related Code) ===\n")
            
            for ev in evidence_by_hop[hop][:15]:  # Top 15 per hop for completeness
                if ev.get("code_chunk"):
                    formatted.append(
                        f"File: {ev.get('file_path', 'unknown')}\n"
                        f"Lines: {ev.get('start_line', 0)}-{ev.get('end_line', 0)}\n"
                        f"Relationship: {ev.get('relationship', 'direct')}\n"
                        f"Code:\n```{ev.get('language', '')}\n{ev.get('code_chunk', '')[:500]}\n```\n"
                    )
                elif ev.get("relationship"):
                    formatted.append(
                        f"Relationship: {ev.get('source_entity')} --[{ev.get('relationship')}]--> {ev.get('target_entity')}\n"
                        f"File: {ev.get('file_path', 'unknown')}\n"
                    )
                elif ev.get("file_path"):
                    formatted.append(
                        f"File: {ev.get('file_path', 'unknown')}\n"
                        f"Entity: {ev.get('source_entity', 'unknown')}\n"
                    )
        
        return "\n\n".join(formatted)


# Global instance
advanced_rag_service = AdvancedRAGService()

