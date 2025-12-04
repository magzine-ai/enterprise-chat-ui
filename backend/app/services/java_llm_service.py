"""
Java LLM Service for code Q&A with evidence-backed answers.

This service handles code questions using LLM reasoning, retrieves relevant
chunks using the search service, and generates answers with file:line citations.
"""

from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
from app.core.config import settings
from app.services.llm_service import llm_service
from app.services.java_search_service import java_search_service
from app.models.java_chunk import JavaChunk
from app.models.java_repository import JavaRepository
from openai import AsyncOpenAI


class JavaLLMService:
    """
    Service for answering Java code questions using LLM.
    
    Retrieves relevant code chunks, formats context, and generates
    evidence-backed answers with citations.
    """
    
    def __init__(self):
        """Initialize the Java LLM service."""
        self.client = None
        if settings.openai_api_key:
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def answer_code_question(
        self,
        session: Session,
        query: str,
        repository_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Answer a code question using LLM with retrieved context.
        
        Args:
            session: Database session
            query: User's question about the code
            repository_id: Optional repository ID to search within
            conversation_history: Optional conversation history
        
        Returns:
            Dict with answer, evidence chunks, and citations
        """
        # Search for relevant chunks
        search_results = await java_search_service.search_code(
            session=session,
            query=query,
            repository_id=repository_id,
            top_k=5
        )
        
        if not search_results:
            return {
                'answer': "I couldn't find any relevant code for your question.",
                'evidence': [],
                'citations': []
            }
        
        # Format context for LLM
        context = self._format_context_for_llm(search_results)
        
        # Build prompt
        system_prompt = """You are a Java code intelligence assistant. Answer questions about Java codebases with precision and evidence.

When answering:
1. Use the provided code context to answer the question
2. Reference specific file paths and line numbers when citing code
3. Explain code behavior, relationships, and patterns clearly
4. If the question is about code flow, trace through the call graph
5. If the question is about types, explain the inheritance hierarchy
6. Be concise but thorough

Format citations as: file_path:start_line-end_line"""

        user_prompt = f"""Context from codebase:

{context}

Question: {query}

Provide a detailed answer with specific file and line number citations."""

        # Generate answer using LLM
        try:
            if not self.client:
                # Fallback if LLM not available
                answer = self._generate_fallback_answer(query, search_results)
            else:
                response = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
                answer = response.choices[0].message.content or ""
            
            # Extract citations from answer
            citations = self._extract_citations(answer, search_results)
            
            return {
                'answer': answer,
                'evidence': search_results[:3],  # Top 3 evidence chunks
                'citations': citations
            }
            
        except Exception as e:
            print(f"❌ Error generating code answer: {e}")
            return {
                'answer': f"I encountered an error while answering your question: {str(e)}",
                'evidence': search_results[:3],
                'citations': []
            }
    
    def _format_context_for_llm(self, search_results: List[Dict[str, Any]]) -> str:
        """
        Format search results as context for LLM.
        
        Args:
            search_results: List of search result dictionaries
        
        Returns:
            Formatted context string
        """
        context_parts = []
        
        for i, result in enumerate(search_results, 1):
            fqn = result.get('fqn', '')
            file_path = result.get('file_path', '')
            code = result.get('code', '')
            summary = result.get('summary', '')
            chunk_type = result.get('type', '')
            start_line = result.get('start_line', 0)
            end_line = result.get('end_line', 0)
            
            context_parts.append(f"\n[{i}] {chunk_type.upper()}: {fqn}")
            context_parts.append(f"File: {file_path}:{start_line}-{end_line}")
            if summary:
                context_parts.append(f"Summary: {summary}")
            context_parts.append(f"Code:\n{code[:500]}")  # Limit code length
            if len(code) > 500:
                context_parts.append("  ... (truncated)")
        
        return "\n".join(context_parts)
    
    def _extract_citations(
        self,
        answer: str,
        search_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract citations from answer text.
        
        Args:
            answer: Generated answer text
            search_results: Search results used for context
        
        Returns:
            List of citation dictionaries
        """
        citations = []
        
        # Look for file:line patterns in answer
        import re
        citation_pattern = r'([^\s:]+):(\d+)(?:-(\d+))?'
        matches = re.finditer(citation_pattern, answer)
        
        for match in matches:
            file_path = match.group(1)
            start_line = int(match.group(2))
            end_line = int(match.group(3)) if match.group(3) else start_line
            
            # Find matching search result
            for result in search_results:
                if result.get('file_path') == file_path:
                    citations.append({
                        'file_path': file_path,
                        'start_line': start_line,
                        'end_line': end_line,
                        'fqn': result.get('fqn', ''),
                        'code': result.get('code', '')
                    })
                    break
        
        return citations
    
    def _generate_fallback_answer(
        self,
        query: str,
        search_results: List[Dict[str, Any]]
    ) -> str:
        """
        Generate a basic answer when LLM is not available.
        
        Args:
            query: User's question
            search_results: Search results
        
        Returns:
            Basic answer text
        """
        if not search_results:
            return "No relevant code found."
        
        top_result = search_results[0]
        fqn = top_result.get('fqn', '')
        file_path = top_result.get('file_path', '')
        summary = top_result.get('summary', '')
        
        answer = f"Based on the codebase, I found: {fqn}\n"
        answer += f"Location: {file_path}\n"
        if summary:
            answer += f"Summary: {summary}\n"
        answer += "\nFor more details, please enable LLM integration."
        
        return answer
    
    async def open_file(
        self,
        session: Session,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieve source code from a file.
        
        Args:
            session: Database session
            file_path: Path to the file
            start_line: Optional start line
            end_line: Optional end line
        
        Returns:
            Dict with file content and metadata
        """
        try:
            # Find chunks in this file
            statement = select(JavaChunk).where(JavaChunk.file_path == file_path)
            chunks = session.exec(statement).all()
            
            if not chunks:
                return {'error': 'File not found in indexed codebase'}
            
            # If lines specified, find specific chunk
            if start_line and end_line:
                for chunk in chunks:
                    if chunk.start_line <= start_line <= chunk.end_line:
                        return {
                            'file_path': file_path,
                            'start_line': chunk.start_line,
                            'end_line': chunk.end_line,
                            'code': chunk.code,
                            'fqn': chunk.fqn,
                            'summary': chunk.summary
                        }
            
            # Return first chunk (or aggregate all chunks)
            first_chunk = chunks[0]
            return {
                'file_path': file_path,
                'start_line': first_chunk.start_line,
                'end_line': first_chunk.end_line,
                'code': first_chunk.code,
                'fqn': first_chunk.fqn,
                'summary': first_chunk.summary,
                'total_chunks': len(chunks)
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    async def summarize_chunk(
        self,
        session: Session,
        chunk_id: int
    ) -> Dict[str, Any]:
        """
        Get or generate summary for a chunk.
        
        Args:
            session: Database session
            chunk_id: Chunk ID
        
        Returns:
            Dict with summary and metadata
        """
        chunk = session.get(JavaChunk, chunk_id)
        if not chunk:
            return {'error': 'Chunk not found'}
        
        summary = chunk.summary
        if not summary and self.client:
            # Generate summary using LLM
            try:
                response = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Summarize this Java code in 2-3 sentences:\n\n{chunk.code[:500]}"
                        }
                    ],
                    temperature=0.3,
                    max_tokens=150
                )
                summary = response.choices[0].message.content or ""
                
                # Save summary
                chunk.summary = summary
                session.add(chunk)
                session.commit()
            except Exception as e:
                print(f"⚠️ Error generating summary: {e}")
        
        return {
            'chunk_id': chunk_id,
            'fqn': chunk.fqn,
            'summary': summary or "No summary available",
            'type': chunk.type
        }
    
    async def find_usages(
        self,
        session: Session,
        symbol: str,
        repository_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find where a symbol is used in the codebase.
        
        Args:
            session: Database session
            symbol: Symbol name (class, method, etc.)
            repository_id: Optional repository filter
        
        Returns:
            List of usage locations
        """
        statement = select(JavaChunk)
        
        if repository_id:
            statement = statement.where(JavaChunk.repository_id == repository_id)
        
        all_chunks = session.exec(statement).all()
        
        usages = []
        symbol_lower = symbol.lower()
        
        for chunk in all_chunks:
            # Check if symbol appears in code
            if symbol_lower in chunk.code.lower() or symbol_lower in chunk.fqn.lower():
                usages.append({
                    'chunk_id': chunk.id,
                    'fqn': chunk.fqn,
                    'file_path': chunk.file_path,
                    'start_line': chunk.start_line,
                    'end_line': chunk.end_line,
                    'type': chunk.type
                })
        
        return usages
    
    async def get_call_graph(
        self,
        session: Session,
        method_id: int
    ) -> Dict[str, Any]:
        """
        Get call graph context for a method.
        
        Args:
            session: Database session
            method_id: Method chunk ID
        
        Returns:
            Dict with call graph information
        """
        chunk = session.get(JavaChunk, method_id)
        if not chunk or chunk.type != "method":
            return {'error': 'Method not found'}
        
        callers = chunk.get_callers()
        callees = chunk.get_callees()
        
        # Get details for callers and callees
        caller_details = []
        for caller_fqn in callers[:10]:
            caller_chunk = session.exec(
                select(JavaChunk).where(JavaChunk.fqn == caller_fqn)
            ).first()
            if caller_chunk:
                caller_details.append({
                    'fqn': caller_chunk.fqn,
                    'file_path': caller_chunk.file_path,
                    'start_line': caller_chunk.start_line
                })
        
        callee_details = []
        for callee_fqn in callees[:10]:
            callee_chunk = session.exec(
                select(JavaChunk).where(JavaChunk.fqn == callee_fqn)
            ).first()
            if callee_chunk:
                callee_details.append({
                    'fqn': callee_chunk.fqn,
                    'file_path': callee_chunk.file_path,
                    'start_line': callee_chunk.start_line
                })
        
        return {
            'method': {
                'fqn': chunk.fqn,
                'file_path': chunk.file_path,
                'start_line': chunk.start_line
            },
            'callers': caller_details,
            'callees': callee_details
        }


# Global instance
java_llm_service = JavaLLMService()

