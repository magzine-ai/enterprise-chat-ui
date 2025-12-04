"""
Java Code Intelligence API endpoints.

Provides endpoints for repository management, code search, and Q&A.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.core.database import get_session
from app.api.auth import get_current_user
from app.models.java_repository import (
    JavaRepository,
    JavaRepositoryCreate,
    JavaRepositoryRead,
    RepositoryIndexStatus
)
from app.models.java_chunk import JavaChunk, JavaChunkRead
from app.services.repository_manager import repository_manager
from app.services.java_search_service import java_search_service
from app.services.java_llm_service import java_llm_service
import asyncio
from typing import Annotated

router = APIRouter(prefix="/java", tags=["java-code"])


# Request/Response Models
class RepositoryIndexRequest(BaseModel):
    incremental: bool = True


class SearchRequest(BaseModel):
    query: str
    repository_id: Optional[int] = None
    top_k: int = 10
    chunk_type: Optional[str] = None


class AskRequest(BaseModel):
    query: str
    repository_id: Optional[int] = None


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int


class AskResponse(BaseModel):
    answer: str
    evidence: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]


# Repository Endpoints
@router.post("/repositories", response_model=JavaRepositoryRead)
async def register_repository(
    repository: JavaRepositoryCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Register a new Java repository for indexing.
    
    Args:
        repository: Repository creation data
        session: Database session
        current_user: Current authenticated user
    
    Returns:
        Created repository object
    """
    try:
        repo = repository_manager.register_repository(
            session=session,
            name=repository.name,
            local_path=repository.local_path,
            description=repository.description
        )
        return repo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering repository: {str(e)}")


@router.get("/repositories", response_model=List[JavaRepositoryRead])
async def list_repositories(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    List all registered Java repositories.
    
    Returns:
        List of repository objects
    """
    repositories = session.exec(select(JavaRepository)).all()
    return repositories


@router.get("/repositories/{repository_id}", response_model=JavaRepositoryRead)
async def get_repository(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get repository details by ID.
    
    Args:
        repository_id: Repository ID
    
    Returns:
        Repository object
    """
    repository = session.get(JavaRepository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.post("/repositories/{repository_id}/index")
async def trigger_indexing(
    repository_id: int,
    request: RepositoryIndexRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Trigger indexing for a repository.
    
    Args:
        repository_id: Repository ID
        request: Indexing options (incremental flag)
        background_tasks: FastAPI background tasks
        session: Database session
        current_user: Current authenticated user
    
    Returns:
        Status message
    """
    repository = session.get(JavaRepository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Update status to indexing immediately
    repository.status = RepositoryIndexStatus.INDEXING
    session.add(repository)
    session.commit()
    
    # Start indexing in background using proper async task
    async def index_task():
        from app.core.database import engine
        try:
            with Session(engine) as task_session:
                task_repo = task_session.get(JavaRepository, repository_id)
                if task_repo:
                    await repository_manager.index_repository(
                        session=task_session,
                        repository=task_repo,
                        incremental=request.incremental
                    )
        except Exception as e:
            print(f"❌ Error in indexing background task: {e}")
            import traceback
            print(traceback.format_exc())
            # Update status to failed
            with Session(engine) as error_session:
                error_repo = error_session.get(JavaRepository, repository_id)
                if error_repo:
                    error_repo.status = RepositoryIndexStatus.FAILED
                    error_session.add(error_repo)
                    error_session.commit()
    
    # Use asyncio.create_task for proper async execution
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(index_task())
        print(f"🚀 Started indexing task for repository {repository_id}")
    except RuntimeError:
        # Fallback to BackgroundTasks if no event loop
        print(f"⚠️ No event loop found, using BackgroundTasks fallback")
        background_tasks.add_task(index_task)
    except Exception as e:
        print(f"❌ Failed to start indexing task: {e}")
        import traceback
        print(traceback.format_exc())
        # Fallback to BackgroundTasks
        background_tasks.add_task(index_task)
    
    return {
        "message": "Indexing started",
        "repository_id": repository_id,
        "status": "indexing"
    }


@router.get("/repositories/{repository_id}/status")
async def get_indexing_status(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get indexing status for a repository.
    
    Args:
        repository_id: Repository ID
    
    Returns:
        Status information
    """
    repository = session.get(JavaRepository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Count chunks
    from app.models.java_chunk import JavaChunk
    chunk_count = len(session.exec(
        select(JavaChunk).where(JavaChunk.repository_id == repository_id)
    ).all())
    
    return {
        "repository_id": repository_id,
        "status": repository.status,
        "last_indexed_at": repository.last_indexed_at,
        "chunk_count": chunk_count
    }


@router.delete("/repositories/{repository_id}")
async def delete_repository(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Delete a repository and all its chunks.
    
    Args:
        repository_id: Repository ID
    
    Returns:
        Success message
    """
    repository = session.get(JavaRepository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Delete all chunks
    from app.models.java_chunk import JavaChunk
    from app.services.opensearch_service import opensearch_service
    from app.core.config import settings
    
    chunks = session.exec(
        select(JavaChunk).where(JavaChunk.repository_id == repository_id)
    ).all()
    
    # Delete from OpenSearch if enabled
    if settings.java_opensearch_enabled and opensearch_service.is_available():
        await opensearch_service.delete_java_chunks_by_repository(repository_id)
    
    # Delete from database
    for chunk in chunks:
        session.delete(chunk)
    
    session.delete(repository)
    session.commit()
    
    return {"message": "Repository deleted successfully"}


# Search Endpoints
@router.post("/search", response_model=SearchResponse)
async def search_code(
    request: SearchRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Search Java code using hybrid search.
    
    Args:
        request: Search request with query and filters
        session: Database session
        current_user: Current authenticated user
    
    Returns:
        Search results with scores
    """
    try:
        results = await java_search_service.search_code(
            session=session,
            query=request.query,
            repository_id=request.repository_id,
            top_k=request.top_k,
            chunk_type=request.chunk_type
        )
        
        return SearchResponse(
            results=results,
            total=len(results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching code: {str(e)}")


@router.get("/chunks/{chunk_id}", response_model=JavaChunkRead)
async def get_chunk(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get chunk details by ID.
    
    Args:
        chunk_id: Chunk ID
    
    Returns:
        Chunk object with parsed JSON fields
    """
    chunk = session.get(JavaChunk, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    # Convert to read model with parsed fields
    return JavaChunkRead(
        id=chunk.id,
        type=chunk.type,
        fqn=chunk.fqn,
        file_path=chunk.file_path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        code=chunk.code,
        summary=chunk.summary,
        imports=chunk.get_imports(),
        annotations=chunk.get_annotations(),
        callers=chunk.get_callers(),
        callees=chunk.get_callees(),
        implemented_interfaces=chunk.get_implemented_interfaces(),
        extended_class=chunk.extended_class,
        test_references=chunk.get_test_references(),
        repository_id=chunk.repository_id,
        last_modified=chunk.last_modified,
        created_at=chunk.created_at,
        updated_at=chunk.updated_at
    )


@router.get("/chunks/{chunk_id}/callers")
async def get_callers(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get callers of a method.
    
    Args:
        chunk_id: Method chunk ID
    
    Returns:
        List of caller chunks
    """
    try:
        callers = await java_search_service.expand_by_callers(
            session=session,
            chunk_id=chunk_id
        )
        return {"callers": callers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting callers: {str(e)}")


@router.get("/chunks/{chunk_id}/callees")
async def get_callees(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get callees of a method.
    
    Args:
        chunk_id: Method chunk ID
    
    Returns:
        List of callee chunks
    """
    try:
        callees = await java_search_service.expand_by_callees(
            session=session,
            chunk_id=chunk_id
        )
        return {"callees": callees}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting callees: {str(e)}")


@router.get("/chunks/{chunk_id}/hierarchy")
async def get_type_hierarchy(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get type hierarchy for a class.
    
    Args:
        chunk_id: Class chunk ID
    
    Returns:
        Type hierarchy information
    """
    try:
        hierarchy = await java_search_service.expand_by_type_hierarchy(
            session=session,
            chunk_id=chunk_id
        )
        return {"hierarchy": hierarchy}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting hierarchy: {str(e)}")


# Code Q&A Endpoints
@router.post("/ask", response_model=AskResponse)
async def ask_code_question(
    request: AskRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Ask a question about Java code (standalone endpoint).
    
    Args:
        request: Question request
        session: Database session
        current_user: Current authenticated user
    
    Returns:
        Answer with evidence and citations
    """
    try:
        result = await java_llm_service.answer_code_question(
            session=session,
            query=request.query,
            repository_id=request.repository_id
        )
        return AskResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error answering question: {str(e)}")


@router.get("/file")
async def open_file(
    file_path: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
):
    """
    Retrieve source code from a file.
    
    Args:
        file_path: Path to the file
        start_line: Optional start line
        end_line: Optional end line
    
    Returns:
        File content and metadata
    """
    try:
        result = await java_llm_service.open_file(
            session=session,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error opening file: {str(e)}")


@router.get("/chunks/{chunk_id}/summary")
async def summarize_chunk(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get or generate summary for a chunk.
    
    Args:
        chunk_id: Chunk ID
    
    Returns:
        Summary information
    """
    try:
        result = await java_llm_service.summarize_chunk(
            session=session,
            chunk_id=chunk_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error summarizing chunk: {str(e)}")


@router.get("/usages")
async def find_usages(
    symbol: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
    repository_id: Optional[int] = None,
):
    """
    Find where a symbol is used in the codebase.
    
    Args:
        symbol: Symbol name (class, method, etc.)
        repository_id: Optional repository filter
    
    Returns:
        List of usage locations
    """
    try:
        usages = await java_llm_service.find_usages(
            session=session,
            symbol=symbol,
            repository_id=repository_id
        )
        return {"usages": usages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding usages: {str(e)}")


@router.get("/chunks/{chunk_id}/call-graph")
async def get_call_graph(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get call graph context for a method.
    
    Args:
        chunk_id: Method chunk ID
    
    Returns:
        Call graph information
    """
    try:
        graph = await java_llm_service.get_call_graph(
            session=session,
            method_id=chunk_id
        )
        return graph
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting call graph: {str(e)}")

