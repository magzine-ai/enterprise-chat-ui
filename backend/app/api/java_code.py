"""
Java Code Intelligence API endpoints.

Provides endpoints for repository management, code search, and Q&A.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging
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
from app.services.graph_service import graph_service
import asyncio
from typing import Annotated

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/java", tags=["java-code"])


# Request/Response Models
class RepositoryIndexRequest(BaseModel):
    incremental: bool = True


class SearchRequest(BaseModel):
    query: str
    repository_id: Optional[int] = None
    top_k: int = 10
    chunk_type: Optional[str] = None
    language: Optional[str] = None  # Filter by language
    use_exhaustive: bool = False  # Use exhaustive multi-hop search
    use_case: Optional[str] = None  # Use case type (migration, impact_analysis, etc.)


class AskRequest(BaseModel):
    query: str
    repository_id: Optional[int] = None
    use_exhaustive: bool = False  # Use exhaustive multi-hop search
    use_case: Optional[str] = None  # Use case type


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int


class AskResponse(BaseModel):
    answer: str
    evidence: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    completeness_check: Optional[Dict[str, Any]] = None  # Completeness verification
    total_evidence_pieces: Optional[int] = None
    use_case: Optional[str] = None


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
            github_url=repository.github_url,
            github_branch=repository.github_branch or "main",
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
    
    # Parse languages if available
    import json
    languages = []
    if repository.languages:
        try:
            languages = json.loads(repository.languages)
        except:
            pass
    
    return {
        "repository_id": repository_id,
        "status": repository.status,
        "last_indexed_at": repository.last_indexed_at,
        "chunk_count": chunk_count,
        "file_count": repository.file_count,
        "languages": languages
    }


@router.get("/repositories/{repository_id}/metadata")
async def get_repository_metadata(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get comprehensive repository metadata.
    
    Args:
        repository_id: Repository ID
    
    Returns:
        Repository metadata including file count, languages, graph stats
    """
    repository = session.get(JavaRepository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    from app.models.java_chunk import JavaChunk
    import json
    
    # Count chunks by type
    chunks = session.exec(
        select(JavaChunk).where(JavaChunk.repository_id == repository_id)
    ).all()
    
    chunk_count = len(chunks)
    method_count = sum(1 for c in chunks if c.type == "method")
    class_count = sum(1 for c in chunks if c.type == "class")
    file_count = len(set(c.file_path for c in chunks))
    
    # Parse languages
    languages = []
    if repository.languages:
        try:
            languages = json.loads(repository.languages)
        except:
            pass
    
    # Get graph stats for this repository
    # Note: Graph must be built first using POST /java/repositories/{id}/build-graph
    graph_stats = {}
    try:
        # Get all graph stats (graph is global)
        all_stats = graph_service.get_graph_stats()
        
        # Filter by repository_id if graph exists
        if graph_service.graph is not None and all_stats.get("nodes", 0) > 0:
            # Count nodes and edges for this specific repository
            repo_nodes = sum(1 for n, data in graph_service.graph.nodes(data=True) 
                           if data.get('repository_id') == repository_id)
            repo_edges = sum(1 for u, v, data in graph_service.graph.edges(data=True)
                           if (graph_service.graph.nodes[u].get('repository_id') == repository_id or
                               graph_service.graph.nodes[v].get('repository_id') == repository_id))
            graph_stats = {
                "nodes": repo_nodes,
                "edges": repo_edges
            }
        else:
            # Graph not built or empty
            graph_stats = {
                "nodes": 0,
                "edges": 0
            }
    except Exception as e:
        # If graph stats unavailable, return zeros
        logger.debug(f"Could not get graph stats for repository {repository_id}: {e}")
        graph_stats = {
            "nodes": 0,
            "edges": 0
        }
    
    return {
        "repository_id": repository_id,
        "name": repository.name,
        "description": repository.description,
        "status": repository.status,
        "last_indexed_at": repository.last_indexed_at,
        "created_at": repository.created_at,
        "updated_at": repository.updated_at,
        "github_url": repository.github_url,
        "local_path": repository.local_path,
        "file_count": file_count,
        "chunk_count": chunk_count,
        "method_count": method_count,
        "class_count": class_count,
        "languages": languages,
        "graph_stats": graph_stats
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
    Search code using hybrid search with multi-language support.
    Supports both standard and exhaustive multi-hop search.
    
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
            chunk_type=request.chunk_type,
            use_exhaustive=request.use_exhaustive,
            use_case=request.use_case
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
    Ask a question about code with multi-language support.
    Supports both standard and exhaustive multi-hop search.
    
    Args:
        request: Question request with optional exhaustive search flags
        session: Database session
        current_user: Current authenticated user
    
    Returns:
        Answer with evidence, citations, and completeness check
    """
    try:
        result = await java_llm_service.answer_code_question(
            session=session,
            query=request.query,
            repository_id=request.repository_id,
            use_exhaustive=request.use_exhaustive,
            use_case=request.use_case
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


# Graph Endpoints
@router.post("/repositories/{repository_id}/build-graph")
async def build_knowledge_graph(
    repository_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
    rebuild: bool = False,
):
    """
    Build or rebuild knowledge graph for a repository.
    
    Args:
        repository_id: Repository ID
        rebuild: If True, clear existing graph for this repository before rebuilding
    
    Returns:
        Graph building status
    """
    logger.info(f"📥 Received graph build request for repository {repository_id} (rebuild={rebuild})")
    
    repository = session.get(JavaRepository, repository_id)
    if not repository:
        logger.error(f"❌ Repository {repository_id} not found")
        raise HTTPException(status_code=404, detail="Repository not found")
    
    logger.info(f"✅ Repository found: {repository.name} (ID: {repository_id})")
    
    # Check if graph already exists and we're not rebuilding
    if not rebuild and graph_service.graph_exists(repository_id=repository_id):
        logger.info(f"📂 Graph already exists for repository {repository_id}, attempting to load...")
        if graph_service.load_graph(repository_id=repository_id):
            stats = graph_service.get_graph_stats()
            # Filter stats for this repository
            if graph_service.graph is not None:
                repo_nodes = sum(1 for n, data in graph_service.graph.nodes(data=True) 
                               if data.get('repository_id') == repository_id)
                repo_edges = sum(1 for u, v, data in graph_service.graph.edges(data=True)
                               if (graph_service.graph.nodes[u].get('repository_id') == repository_id or
                                   graph_service.graph.nodes[v].get('repository_id') == repository_id))
                logger.info(f"✅ Loaded existing graph: {repo_nodes} nodes, {repo_edges} edges")
                return {
                    "success": True,
                    "repository_id": repository_id,
                    "status": "loaded",
                    "rebuild": False,
                    "message": f"Graph loaded from disk: {repo_nodes} nodes, {repo_edges} edges",
                    "graph_stats": {
                        "nodes": repo_nodes,
                        "edges": repo_edges
                    }
                }
            else:
                logger.warning(f"⚠️  Graph loaded but is None, will rebuild")
        else:
            logger.warning(f"⚠️  Failed to load existing graph, will rebuild")
    
    try:
        from app.models.job import Job, JobStatus
        from app.services.job_service import JobService
        import uuid
        
        # Create async job
        logger.info(f"🔄 Creating async job for graph {'rebuild' if rebuild else 'build'}...")
        job_service = JobService(session)
        job = await job_service.create_job(
            job_type="build_graph",
            params={"repository_id": repository_id, "rebuild": rebuild},
            conversation_id=None
        )
        
        action = "rebuilding" if rebuild else "building"
        logger.info(f"✅ Graph {action} job created successfully: job_id={job.job_id}, repository_id={repository_id}, status={job.status}")
        logger.info(f"📋 Job {job.job_id} is now queued and will start processing shortly")
        
        return {
            "success": True,
            "job_id": job.job_id,
            "repository_id": repository_id,
            "status": job.status,
            "rebuild": rebuild,
            "message": f"Graph {action} job created. Use job_id to track progress."
        }
    except Exception as e:
        logger.error(f"❌ Error creating graph building job for repository {repository_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating graph building job: {str(e)}")


@router.get("/graph/stats")
async def get_graph_stats(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Get knowledge graph statistics.
    
    Returns:
        Graph statistics
    """
    return graph_service.get_graph_stats()


@router.get("/graph/chunks/{chunk_id}/related")
async def get_related_code(
    chunk_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
    max_depth: int = 2,
    include_cross_repo: bool = True,
):
    """
    Get related code using graph traversal.
    
    Args:
        chunk_id: Starting chunk ID
        max_depth: Maximum traversal depth
        include_cross_repo: Whether to include cross-repository relationships
    
    Returns:
        List of related code chunks
    """
    try:
        related = await graph_service.find_related_code(
            session=session,
            chunk_id=chunk_id,
            max_depth=max_depth,
            include_cross_repo=include_cross_repo
        )
        return {"related": related}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting related code: {str(e)}")


@router.get("/graph/file/{file_path:path}/dependencies")
async def get_file_dependencies(
    file_path: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
    repository_id: Optional[int] = None,
    depth: int = 2,
):
    """
    Get file dependencies using graph.
    
    Args:
        file_path: File path
        repository_id: Optional repository filter
        depth: Traversal depth
    
    Returns:
        File dependencies
    """
    try:
        deps = await graph_service.get_file_dependencies(
            session=session,
            file_path=file_path,
            repository_id=repository_id,
            depth=depth
        )
        return deps
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting file dependencies: {str(e)}")


class GraphVisualizeRequest(BaseModel):
    query: str
    repository_id: Optional[int] = None
    max_nodes: int = 50
    max_depth: int = 2


@router.post("/graph/visualize")
async def visualize_graph(
    request: GraphVisualizeRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Generate graph visualization data based on search query.
    
    Args:
        query: Search query to find starting nodes
        repository_id: Optional repository filter
        max_nodes: Maximum number of nodes to return
        max_depth: Maximum graph traversal depth
    
    Returns:
        Graph visualization data (nodes and edges)
    """
    try:
        # Ensure graph is built for this repository
        if request.repository_id:
            # Try to load graph if it exists but not in memory
            if graph_service.graph is None or graph_service.graph.number_of_nodes() == 0:
                if graph_service.graph_exists(repository_id=request.repository_id):
                    logger.info(f"📂 Graph not in memory, loading from disk for repository {request.repository_id}")
                    if graph_service.load_graph(repository_id=request.repository_id):
                        logger.info(f"✅ Graph loaded successfully for repository {request.repository_id}")
                    else:
                        logger.warning(f"⚠️  Failed to load graph for repository {request.repository_id}")
            
            # Check if graph has nodes for this repository
            all_stats = graph_service.get_graph_stats()
            if graph_service.graph is not None:
                repo_nodes = sum(1 for n, data in graph_service.graph.nodes(data=True) 
                               if data.get('repository_id') == request.repository_id)
                if repo_nodes == 0:
                    # Graph not built yet, return empty with helpful message
                    logger.warning(f"Graph not built for repository {request.repository_id}")
                    return {
                        "nodes": [], 
                        "edges": [],
                        "error": "Graph not built yet. Please build the knowledge graph first."
                    }
            elif all_stats.get("nodes", 0) == 0:
                # Graph not initialized
                return {
                    "nodes": [], 
                    "edges": [],
                    "error": "Graph not built yet. Please build the knowledge graph first."
                }
        
        # First, try to find nodes directly in the graph
        graph_nodes = graph_service.search_nodes_by_query(
            query=request.query,
            repository_id=request.repository_id,
            max_results=min(10, request.max_nodes)
        )
        
        # Also search using the search service for semantic matches
        search_results = await java_search_service.search_code(
            session=session,
            query=request.query,
            repository_id=request.repository_id,
            top_k=min(10, request.max_nodes)
        )
        
        # Combine results: prefer graph nodes (exact matches), then search results
        all_chunk_ids = set()
        initial_chunks = []
        
        # Add graph nodes first (exact FQN matches)
        for graph_node in graph_nodes:
            chunk_id = graph_node.get('chunk_id')
            if chunk_id and chunk_id not in all_chunk_ids:
                all_chunk_ids.add(chunk_id)
                initial_chunks.append({
                    'id': chunk_id,
                    'fqn': graph_node.get('fqn', ''),
                    'chunk_type': graph_node.get('type', 'unknown'),
                    'file_path': graph_node.get('file_path', ''),
                    'repository_id': graph_node.get('repository_id'),
                    'source': 'graph'
                })
        
        # Add search results that aren't already included
        for result in search_results:
            chunk_id = result.get("id")
            if chunk_id and chunk_id not in all_chunk_ids:
                all_chunk_ids.add(chunk_id)
                initial_chunks.append({
                    'id': chunk_id,
                    'fqn': result.get("fqn", result.get("file_path", "")),
                    'chunk_type': result.get("chunk_type", "unknown"),
                    'file_path': result.get("file_path", ""),
                    'repository_id': result.get("repository_id"),
                    'source': 'search'
                })
        
        if not initial_chunks:
            logger.warning(f"No chunks found for query '{request.query}' in repository {request.repository_id}")
            return {
                "nodes": [],
                "edges": [],
                "error": f"No results found for query '{request.query}'. Try a different search term or check if the graph is built."
            }
        
        logger.info(f"Found {len(initial_chunks)} initial chunks for visualization (graph: {len(graph_nodes)}, search: {len(search_results)})")
        
        # Build graph from search results
        nodes = []
        edges = []
        node_ids = set()
        chunk_to_node_id = {}  # Map chunk_id to graph node_id
        
        # First, add all initial nodes
        for result in initial_chunks[:10]:  # Limit initial nodes
            chunk_id = result.get("id")
            if not chunk_id or chunk_id in node_ids:
                continue
            
            node_ids.add(chunk_id)
            graph_node_id = f"chunk_{chunk_id}"
            chunk_to_node_id[chunk_id] = graph_node_id
            
            nodes.append({
                "id": chunk_id,
                "label": result.get("fqn", result.get("file_path", "")),
                "type": result.get("chunk_type", "unknown"),
                "file_path": result.get("file_path", ""),
                "repository_id": result.get("repository_id")
            })
        
        logger.info(f"Added {len(nodes)} initial nodes, now finding relationships...")
        
        # First, add edges between initial nodes if they're connected in the graph
        initial_edges_count = 0
        if graph_service.graph is not None:
            logger.info(f"Checking for edges between {len(initial_chunks)} initial nodes...")
            for i, result1 in enumerate(initial_chunks[:10]):
                chunk_id1 = result1.get("id")
                if not chunk_id1:
                    continue
                node_id1 = f"chunk_{chunk_id1}"
                
                if node_id1 not in graph_service.graph:
                    continue
                
                for result2 in initial_chunks[i+1:10]:
                    chunk_id2 = result2.get("id")
                    if not chunk_id2:
                        continue
                    node_id2 = f"chunk_{chunk_id2}"
                    
                    if node_id2 not in graph_service.graph:
                        continue
                    
                    # Check if nodes are connected in graph (both directions)
                    if graph_service.graph.has_edge(node_id1, node_id2):
                        edge_data = graph_service.graph.get_edge_data(node_id1, node_id2)
                        if edge_data:
                            for edge_key, edge_info in edge_data.items():
                                edges.append({
                                    "source": chunk_id1,
                                    "target": chunk_id2,
                                    "type": edge_info.get("relationship", "related")
                                })
                                initial_edges_count += 1
                                logger.debug(f"Added edge between initial nodes: {chunk_id1} -> {chunk_id2}")
                                break
                    elif graph_service.graph.has_edge(node_id2, node_id1):
                        edge_data = graph_service.graph.get_edge_data(node_id2, node_id1)
                        if edge_data:
                            for edge_key, edge_info in edge_data.items():
                                edges.append({
                                    "source": chunk_id2,
                                    "target": chunk_id1,
                                    "type": edge_info.get("relationship", "related")
                                })
                                initial_edges_count += 1
                                logger.debug(f"Added edge between initial nodes: {chunk_id2} -> {chunk_id1}")
                                break
            
            if initial_edges_count > 0:
                logger.info(f"✅ Added {initial_edges_count} edges between initial nodes")
            else:
                logger.warning(f"⚠️  No edges found between any of the {len(initial_chunks)} initial nodes")
        
        # Now find relationships for each node - use direct graph traversal
        if graph_service.graph is not None:
            logger.info(f"Traversing graph to find relationships for {len(initial_chunks)} initial nodes...")
            logger.info(f"Graph has {graph_service.graph.number_of_nodes()} nodes and {graph_service.graph.number_of_edges()} edges total")
            
            for result in initial_chunks[:10]:
                chunk_id = result.get("id")
                if not chunk_id:
                    continue
                
                graph_node_id = f"chunk_{chunk_id}"
                
                # Check if this node exists in the graph
                if graph_node_id not in graph_service.graph:
                    logger.warning(f"Node {graph_node_id} (chunk_id={chunk_id}, FQN={result.get('fqn', 'unknown')}) not in graph!")
                    continue
                
                edges_added_for_chunk = 0
                
                # Get all neighbors (both successors and predecessors) directly from graph
                successors = list(graph_service.graph.successors(graph_node_id))
                predecessors = list(graph_service.graph.predecessors(graph_node_id))
                all_neighbors = successors + predecessors
                
                logger.info(f"Node {graph_node_id} (chunk_id={chunk_id}) has {len(successors)} successors and {len(predecessors)} predecessors")
                
                if len(all_neighbors) == 0:
                    logger.warning(f"Node {graph_node_id} (FQN={result.get('fqn', 'unknown')}) has no neighbors in graph!")
                    # Check if this is a method/class that should have relationships
                    chunk_type = result.get('chunk_type', 'unknown')
                    if chunk_type in ['method', 'class']:
                        logger.warning(f"⚠️  {chunk_type} node has no edges - graph may not have relationships built for this node")
                
                for neighbor_node_id in all_neighbors[:15]:  # Increased limit
                    # Get neighbor chunk_id from graph node data
                    neighbor_data = graph_service.graph.nodes[neighbor_node_id]
                    neighbor_chunk_id = neighbor_data.get('chunk_id')
                    
                    if not neighbor_chunk_id:
                        logger.debug(f"Neighbor {neighbor_node_id} has no chunk_id in graph data")
                        continue
                    
                    # Get edge data to determine relationship type
                    edge_data = None
                    direction = "outgoing"
                    
                    if graph_service.graph.has_edge(graph_node_id, neighbor_node_id):
                        edge_data = graph_service.graph.get_edge_data(graph_node_id, neighbor_node_id)
                        direction = "outgoing"
                    elif graph_service.graph.has_edge(neighbor_node_id, graph_node_id):
                        edge_data = graph_service.graph.get_edge_data(neighbor_node_id, graph_node_id)
                        direction = "incoming"
                    
                    if not edge_data:
                        logger.debug(f"No edge data found between {graph_node_id} and {neighbor_node_id}")
                        continue
                    
                    # Extract relationship type from edge data
                    rel_type = "related"
                    for edge_key, edge_info in edge_data.items():
                        rel_type = edge_info.get('relationship', 'related')
                        break
                    
                    # Add neighbor node if not already present (but limit to nodes we want to show)
                    neighbor_added = False
                    if neighbor_chunk_id not in node_ids:
                        # Only add if we haven't exceeded max nodes
                        if len(nodes) < request.max_nodes:
                            node_ids.add(neighbor_chunk_id)
                            neighbor_chunk = session.get(JavaChunk, neighbor_chunk_id)
                            if neighbor_chunk:
                                nodes.append({
                                    "id": neighbor_chunk_id,
                                    "label": neighbor_data.get('fqn', neighbor_chunk.fqn),
                                    "type": neighbor_data.get('type', neighbor_chunk.type),
                                    "file_path": neighbor_data.get('file_path', neighbor_chunk.file_path),
                                    "repository_id": neighbor_data.get('repository_id', neighbor_chunk.repository_id)
                                })
                                chunk_to_node_id[neighbor_chunk_id] = neighbor_node_id
                                neighbor_added = True
                    
                    # Add edge if the neighbor is in our visualization (either was already there or we just added it)
                    # OR if the neighbor is one of our initial nodes (even if we're not adding it to visualization)
                    if neighbor_chunk_id in node_ids or any(r.get("id") == neighbor_chunk_id for r in initial_chunks):
                        if direction == "incoming":
                            edge = {
                                "source": neighbor_chunk_id,
                                "target": chunk_id,
                                "type": rel_type
                            }
                        else:
                            edge = {
                                "source": chunk_id,
                                "target": neighbor_chunk_id,
                                "type": rel_type
                            }
                        
                        edges.append(edge)
                        edges_added_for_chunk += 1
                        logger.debug(f"Added edge: {edge['source']} -> {edge['target']} (type: {rel_type}, direction: {direction}, neighbor_added: {neighbor_added})")
                
                if edges_added_for_chunk > 0:
                    logger.info(f"✅ Added {edges_added_for_chunk} edges for chunk {chunk_id} (FQN: {result.get('fqn', 'unknown')})")
                else:
                    logger.warning(f"⚠️  No edges added for chunk {chunk_id} (FQN: {result.get('fqn', 'unknown')}) - node has {len(all_neighbors)} neighbors but none were added")
        else:
            logger.warning("Graph is None, cannot find relationships")
        
        # Also add edges between initial nodes if they're connected in the graph
        initial_edges_added = 0
        if graph_service.graph is not None:
            logger.info(f"Checking for edges between {len(initial_chunks)} initial nodes...")
            for i, result1 in enumerate(initial_chunks[:10]):
                chunk_id1 = result1.get("id")
                if not chunk_id1:
                    continue
                node_id1 = f"chunk_{chunk_id1}"
                
                for result2 in initial_chunks[i+1:10]:
                    chunk_id2 = result2.get("id")
                    if not chunk_id2:
                        continue
                    node_id2 = f"chunk_{chunk_id2}"
                    
                    # Check if nodes are connected in graph
                    if graph_service.graph.has_edge(node_id1, node_id2):
                        edge_data = graph_service.graph.get_edge_data(node_id1, node_id2)
                        if edge_data:
                            for edge_key, edge_info in edge_data.items():
                                edges.append({
                                    "source": chunk_id1,
                                    "target": chunk_id2,
                                    "type": edge_info.get("relationship", "related")
                                })
                                initial_edges_added += 1
                                logger.debug(f"Added edge between initial nodes: {chunk_id1} -> {chunk_id2}")
                                break
                    elif graph_service.graph.has_edge(node_id2, node_id1):
                        edge_data = graph_service.graph.get_edge_data(node_id2, node_id1)
                        if edge_data:
                            for edge_key, edge_info in edge_data.items():
                                edges.append({
                                    "source": chunk_id2,
                                    "target": chunk_id1,
                                    "type": edge_info.get("relationship", "related")
                                })
                                initial_edges_added += 1
                                logger.debug(f"Added edge between initial nodes: {chunk_id2} -> {chunk_id1}")
                                break
            
            if initial_edges_added > 0:
                logger.info(f"Added {initial_edges_added} edges between initial nodes")
            else:
                logger.info(f"No edges found between initial nodes")
        
        # Remove duplicate edges and filter to only include edges where both nodes are in the visualization
        node_id_set = {node["id"] for node in nodes}
        seen_edges = set()
        valid_edges = []
        
        for edge in edges:
            # Only include edges where both source and target are in the nodes list
            if edge["source"] not in node_id_set or edge["target"] not in node_id_set:
                logger.debug(f"Skipping edge with missing node: {edge['source']} -> {edge['target']}")
                continue
            
            # Remove duplicates
            edge_key = (edge["source"], edge["target"])
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                valid_edges.append(edge)
        
        edges = valid_edges
        logger.info(f"Generated visualization with {len(nodes)} nodes and {len(edges)} edges (after deduplication and filtering)")
        
        # Log sample edges for debugging
        if edges:
            logger.info(f"Sample edges: {edges[:5]}")
            logger.info(f"✅ {len(edges)} edges have valid source/target IDs matching node IDs")
        else:
            logger.warning("⚠️  No edges in visualization! Graph may not have relationships built.")
            # Check if graph has edges at all
            if graph_service.graph is not None:
                total_graph_edges = graph_service.graph.number_of_edges()
                logger.warning(f"Graph has {total_graph_edges} total edges, but none were included in visualization")
                # Check if any of our nodes have edges in the graph
                nodes_with_edges = 0
                for node in nodes[:5]:  # Check first 5 nodes
                    node_id = f"chunk_{node['id']}"
                    if node_id in graph_service.graph:
                        successors = list(graph_service.graph.successors(node_id))
                        predecessors = list(graph_service.graph.predecessors(node_id))
                        if successors or predecessors:
                            nodes_with_edges += 1
                            logger.info(f"Node {node['id']} ({node['label']}) has {len(successors)} successors and {len(predecessors)} predecessors")
                if nodes_with_edges == 0:
                    logger.warning("None of the visualization nodes have edges in the graph")
        
        return {
            "nodes": nodes[:request.max_nodes],
            "edges": edges
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating graph visualization: {str(e)}")

