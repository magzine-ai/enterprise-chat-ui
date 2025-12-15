"""Graph building worker for async knowledge graph construction."""
from sqlmodel import Session, select
from app.models.job import Job, JobStatus
from app.models.java_repository import JavaRepository
from app.services.graph_service import graph_service
from app.core.database import engine
from app.core.event_bus import event_bus
import asyncio
import logging

logger = logging.getLogger(__name__)


async def build_graph_async(job_id: str, repository_id: int):
    """
    Build knowledge graph for a repository (async with progress tracking).
    
    Publishes progress updates via event bus and WebSocket.
    
    Args:
        job_id: Job identifier
        repository_id: Repository ID to build graph for
    """
    logger.info(f"🚀 Starting graph building job {job_id} for repository {repository_id}")
    
    with Session(engine) as session:
        # Get job
        statement = select(Job).where(Job.job_id == job_id)
        job = session.exec(statement).first()
        if not job:
            logger.error(f"❌ Job {job_id} not found in database")
            return
        
        # Get rebuild flag from job params
        job_params = job.get_params()
        rebuild = job_params.get("rebuild", False) if job_params else False
        action = "rebuild" if rebuild else "build"
        logger.info(f"📋 Job {job_id}: {action} mode for repository {repository_id}")
        
        # Get repository
        repository = session.get(JavaRepository, repository_id)
        if not repository:
            error_msg = f"Repository {repository_id} not found"
            logger.error(f"❌ {error_msg}")
            job.status = JobStatus.FAILED
            job.error = error_msg
            session.add(job)
            session.commit()
            await _broadcast_job_update(job_id, job.status, 0, error=job.error)
            return
        
        logger.info(f"📦 Repository found: {repository.name} (ID: {repository_id})")
        
        try:
            # Update status to started
            job.status = JobStatus.STARTED
            job.progress = 0
            session.add(job)
            session.commit()
            
            logger.info(f"▶️  Job {job_id} status changed to STARTED (0% progress)")
            
            # Broadcast start
            action_text = "Rebuilding" if rebuild else "Building"
            await _broadcast_job_update(job_id, job.status, 0, message=f"{action_text} graph...")
            
            # Build graph with progress callbacks
            logger.info(f"🔨 Starting graph construction process for repository {repository_id}")
            success = await _build_graph_with_progress(
                session, repository_id, job_id, job, rebuild
            )
            
            if not success:
                error_msg = "Graph building failed. Check logs for details."
                logger.error(f"❌ Job {job_id} failed: {error_msg}")
                job.status = JobStatus.FAILED
                job.error = error_msg
                job.progress = 0
                session.add(job)
                session.commit()
                await _broadcast_job_update(job_id, job.status, 0, error=job.error)
                return
            
            # Get final graph stats (filter by repository_id manually)
            logger.info(f"📊 Calculating final graph statistics for repository {repository_id}")
            all_stats = graph_service.get_graph_stats()
            # Filter for this repository
            if graph_service.graph is not None:
                repo_nodes = sum(1 for n, data in graph_service.graph.nodes(data=True) 
                               if data.get('repository_id') == repository_id)
                repo_edges = sum(1 for u, v, data in graph_service.graph.edges(data=True)
                               if (graph_service.graph.nodes[u].get('repository_id') == repository_id or
                                   graph_service.graph.nodes[v].get('repository_id') == repository_id))
                stats = {
                    "nodes": repo_nodes,
                    "edges": repo_edges,
                    "available": all_stats.get("available", False)
                }
                logger.info(f"✅ Final stats for repository {repository_id}: {repo_nodes} nodes, {repo_edges} edges")
            else:
                stats = {"nodes": 0, "edges": 0, "available": False}
                logger.warning(f"⚠️  Graph is None, stats are 0")
            
            # Save graph to disk for persistence
            logger.info(f"💾 Saving graph to disk for repository {repository_id}...")
            save_success = graph_service.save_graph(repository_id=repository_id)
            if save_success:
                logger.info(f"✅ Graph saved successfully for repository {repository_id}")
            else:
                logger.warning(f"⚠️  Failed to save graph for repository {repository_id}")
            
            result = {
                "type": "graph_build",
                "repository_id": repository_id,
                "graph_stats": {
                    "nodes": stats.get("nodes", 0),
                    "edges": stats.get("edges", 0),
                    "available": stats.get("available", False)
                },
                "message": f"Graph built successfully: {stats.get('nodes', 0)} nodes, {stats.get('edges', 0)} edges"
            }
            
            # Update job with result
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.set_result(result)
            session.add(job)
            session.commit()
            
            logger.info(f"✅ Job {job_id} completed successfully: {stats.get('nodes', 0)} nodes, {stats.get('edges', 0)} edges")
            
            # Broadcast completion
            await _broadcast_job_update(job_id, job.status, 100, result=result)
            
        except Exception as e:
            logger.error(f"❌ Error building graph for repository {repository_id} in job {job_id}: {e}", exc_info=True)
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.progress = 0
            session.add(job)
            session.commit()
            await _broadcast_job_update(job_id, job.status, 0, error=str(e))


async def _build_graph_with_progress(
    session: Session,
    repository_id: int,
    job_id: str,
    job: Job,
    rebuild: bool = False
) -> bool:
    """
    Build graph with progress updates.
    
    Args:
        session: Database session
        repository_id: Repository ID
        job_id: Job identifier
        job: Job object
        rebuild: If True, clear only this repository's nodes before rebuilding
    
    Returns:
        True if successful, False otherwise
    """
    from app.models.java_chunk import JavaChunk
    
    # Ensure graph is initialized
    if graph_service.graph is None:
        from app.services.graph_service import NETWORKX_AVAILABLE
        import networkx as nx
        if NETWORKX_AVAILABLE:
            graph_service.graph = nx.MultiDiGraph()
        else:
            return False
    
    try:
        # Clear graph: either specific repository (if rebuild) or entire graph
        if rebuild:
            # Clear only this repository's nodes/edges
            logger.info(f"🧹 Clearing existing graph nodes/edges for repository {repository_id} (rebuild mode)")
            nodes_before = graph_service.graph.number_of_nodes() if graph_service.graph is not None else 0
            edges_before = graph_service.graph.number_of_edges() if graph_service.graph is not None else 0
            graph_service.clear_repository_graph(repository_id)
            nodes_after = graph_service.graph.number_of_nodes() if graph_service.graph is not None else 0
            edges_after = graph_service.graph.number_of_edges() if graph_service.graph is not None else 0
            logger.info(f"✅ Cleared {nodes_before - nodes_after} nodes and {edges_before - edges_after} edges for repository {repository_id}")
        else:
            # Clear entire graph (original behavior)
            logger.info(f"🧹 Clearing entire graph (new build)")
            graph_service.graph.clear()
            logger.info(f"✅ Graph cleared, ready for new build")
        
        # Get all chunks
        logger.info(f"📚 Loading chunks from database for repository {repository_id}")
        query = select(JavaChunk).where(JavaChunk.repository_id == repository_id)
        chunks = session.exec(query).all()
        
        if not chunks:
            logger.warning(f"⚠️  No chunks found for repository {repository_id}. Repository may need to be indexed first.")
            return False
        
        total_chunks = len(chunks)
        logger.info(f"📦 Loaded {total_chunks} chunks for repository {repository_id}")
        
        # Progress: 0-30% for adding nodes
        await _update_progress(job_id, job, session, 5, "Loading chunks...")
        logger.info(f"📊 Progress: 5% - Starting to add nodes to graph")
        
        # Add all chunks as nodes
        nodes_added = 0
        logger.info(f"🔨 Adding {total_chunks} chunks as nodes to graph...")
        for i, chunk in enumerate(chunks):
            node_id = f"chunk_{chunk.id}"
            graph_service.graph.add_node(
                node_id,
                type=chunk.type,
                fqn=chunk.fqn,
                repository_id=chunk.repository_id,
                file_path=chunk.file_path,
                chunk_id=chunk.id,
            )
            nodes_added += 1
            
            # Update progress every 100 chunks
            if (i + 1) % 100 == 0 or (i + 1) == total_chunks:
                progress = 5 + int((i + 1) / total_chunks * 25)  # 5-30%
                await _update_progress(
                    job_id, job, session, progress,
                    f"Adding nodes... {nodes_added}/{total_chunks}",
                    nodes=nodes_added,
                    edges=0
                )
                logger.info(f"📊 Progress: {progress}% - Added {nodes_added}/{total_chunks} nodes")
        
        logger.info(f"✅ Phase 1 complete: Added {nodes_added} nodes to graph")
        
        # Progress: 30-90% for adding edges
        # Process method chunks for call relationships
        method_chunks = [c for c in chunks if c.type == "method"]
        total_methods = len(method_chunks)
        logger.info(f"🔗 Phase 2 starting: Processing {total_methods} method chunks to build relationships")
        
        await _update_progress(job_id, job, session, 30, f"Processing {total_methods} methods for relationships...")
        logger.info(f"📊 Progress: 30% - Starting to build relationships (callers, callees, imports)")
        
        edges_added_in_batch = 0
        for i, chunk in enumerate(method_chunks):
            node_id = f"chunk_{chunk.id}"
            callers = chunk.get_callers()
            callees = chunk.get_callees()
            imports = chunk.get_imports()
            
            # Add caller edges
            for caller_fqn in callers:
                try:
                    caller_chunk = graph_service._find_chunk_by_fqn(session, caller_fqn, chunk.repository_id)
                    if caller_chunk:
                        caller_node_id = f"chunk_{caller_chunk.id}"
                        graph_service.graph.add_edge(
                            caller_node_id, node_id,
                            relationship='calls',
                            type='caller'
                        )
                        edges_added_in_batch += 1
                except Exception as e:
                    logger.debug(f"Could not add caller edge for {caller_fqn}: {e}")
            
            # Add callee edges
            for callee_fqn in callees:
                try:
                    callee_chunk = graph_service._find_chunk_by_fqn(session, callee_fqn, chunk.repository_id)
                    if callee_chunk:
                        callee_node_id = f"chunk_{callee_chunk.id}"
                        graph_service.graph.add_edge(
                            node_id, callee_node_id,
                            relationship='calls',
                            type='callee'
                        )
                        edges_added_in_batch += 1
                except Exception as e:
                    logger.debug(f"Could not add callee edge for {callee_fqn}: {e}")
            
            # Add import edges
            for imp in imports:
                try:
                    imported_chunk = graph_service._find_chunk_by_import(session, imp, chunk.repository_id)
                    if imported_chunk:
                        imported_node_id = f"chunk_{imported_chunk.id}"
                        graph_service.graph.add_edge(
                            node_id, imported_node_id,
                            relationship='imports',
                            type='import',
                            import_name=imp
                        )
                        edges_added_in_batch += 1
                except Exception as e:
                    logger.debug(f"Could not add import edge for {imp}: {e}")
            
            # Update progress every 50 methods
            if (i + 1) % 50 == 0 or (i + 1) == total_methods:
                progress = 30 + int((i + 1) / total_methods * 60)  # 30-90%
                # Use actual graph edge count, not just edges_added in this batch
                current_edges = graph_service.graph.number_of_edges()
                await _update_progress(
                    job_id, job, session, progress,
                    f"Building relationships... {i + 1}/{total_methods} methods, {current_edges} edges",
                    nodes=graph_service.graph.number_of_nodes(),
                    edges=current_edges
                )
                logger.info(f"📊 Progress: {progress}% - Processed {i + 1}/{total_methods} methods, {current_edges} edges created")
            
            # Yield control periodically to avoid blocking
            if (i + 1) % 100 == 0:
                await asyncio.sleep(0.01)  # Small yield
        
        logger.info(f"✅ Method relationships complete: {graph_service.graph.number_of_edges()} edges so far")
        
        # Progress: 75-85% for adding class relationships
        class_chunks = [c for c in chunks if c.type == "class"]
        total_classes = len(class_chunks)
        logger.info(f"🔗 Phase 3 starting: Processing {total_classes} class chunks for inheritance/implementation relationships")
        
        await _update_progress(job_id, job, session, 75, f"Processing {total_classes} classes for relationships...")
        
        # Add class relationships (extends, implements) and method-to-class relationships
        for i, chunk in enumerate(class_chunks):
            node_id = f"chunk_{chunk.id}"
            
            # Add extends relationship
            extended_class = chunk.extended_class
            if extended_class:
                try:
                    extended_chunk = graph_service._find_chunk_by_fqn(session, extended_class, chunk.repository_id)
                    if extended_chunk:
                        extended_node_id = f"chunk_{extended_chunk.id}"
                        graph_service.graph.add_edge(
                            node_id, extended_node_id,
                            relationship='extends',
                            type='inheritance'
                        )
                        edges_added_in_batch += 1
                except Exception as e:
                    logger.debug(f"Could not add extends edge for {extended_class}: {e}")
            
            # Add implements relationships
            implemented_interfaces = chunk.get_implemented_interfaces()
            for interface_fqn in implemented_interfaces:
                try:
                    interface_chunk = graph_service._find_chunk_by_fqn(session, interface_fqn, chunk.repository_id)
                    if interface_chunk:
                        interface_node_id = f"chunk_{interface_chunk.id}"
                        graph_service.graph.add_edge(
                            node_id, interface_node_id,
                            relationship='implements',
                            type='implementation'
                        )
                        edges_added_in_batch += 1
                except Exception as e:
                    logger.debug(f"Could not add implements edge for {interface_fqn}: {e}")
            
            # Connect methods to their containing class
            # Find all method chunks in the same file that belong to this class
            class_fqn = chunk.fqn
            methods_in_class = [c for c in chunks if c.type == "method" and c.file_path == chunk.file_path and c.fqn.startswith(class_fqn + ".")]
            for method_chunk in methods_in_class:
                method_node_id = f"chunk_{method_chunk.id}"
                if method_node_id in graph_service.graph:
                    # Add edge from method to class (method belongs to class)
                    graph_service.graph.add_edge(
                        method_node_id, node_id,
                        relationship='belongs_to',
                        type='containment'
                    )
                    edges_added_in_batch += 1
            
            # Update progress every 50 classes
            if (i + 1) % 50 == 0 or (i + 1) == total_classes:
                progress = 75 + int((i + 1) / total_classes * 10)  # 75-85%
                current_edges = graph_service.graph.number_of_edges()
                await _update_progress(
                    job_id, job, session, progress,
                    f"Building class relationships... {i + 1}/{total_classes} classes, {current_edges} edges",
                    nodes=graph_service.graph.number_of_nodes(),
                    edges=current_edges
                )
        
        logger.info(f"✅ Class relationships complete: {graph_service.graph.number_of_edges()} edges so far")
        
        # Progress: 85-90% for adding file relationships
        logger.info(f"🔗 Phase 4: Adding file relationships (connecting chunks in same file)")
        
        await _update_progress(job_id, job, session, 85, "Building file relationships...")
        
        # Group chunks by file_path and connect chunks in the same file
        chunks_by_file = {}
        for chunk in chunks:
            if chunk.file_path not in chunks_by_file:
                chunks_by_file[chunk.file_path] = []
            chunks_by_file[chunk.file_path].append(chunk)
        
        # Connect all chunks in the same file to the file chunk
        file_chunks = [c for c in chunks if c.type == "file"]
        for file_chunk in file_chunks:
            file_node_id = f"chunk_{file_chunk.id}"
            if file_node_id not in graph_service.graph:
                continue
            
            # Connect all chunks in this file to the file chunk
            file_path_chunks = chunks_by_file.get(file_chunk.file_path, [])
            for chunk in file_path_chunks:
                if chunk.id == file_chunk.id:
                    continue
                chunk_node_id = f"chunk_{chunk.id}"
                if chunk_node_id in graph_service.graph:
                    # Add edge from chunk to file (chunk belongs to file)
                    if not graph_service.graph.has_edge(chunk_node_id, file_node_id):
                        graph_service.graph.add_edge(
                            chunk_node_id, file_node_id,
                            relationship='in_file',
                            type='file'
                        )
        
        # Final progress update
        final_nodes = graph_service.graph.number_of_nodes()
        final_edges = graph_service.graph.number_of_edges()
        logger.info(f"✅ Phase 4 complete: Graph built with {final_nodes} nodes, {final_edges} edges")
        logger.info(f"📊 Progress: 95% - Finalizing graph construction")
        
        await _update_progress(
            job_id, job, session, 95,
            f"Graph complete: {final_nodes} nodes, {final_edges} edges",
            nodes=final_nodes,
            edges=final_edges
        )
        
        logger.info(f"🎉 Graph building completed successfully for repository {repository_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to build graph for repository {repository_id}: {e}", exc_info=True)
        return False


async def _update_progress(
    job_id: str,
    job: Job,
    session: Session,
    progress: int,
    message: str = None,
    nodes: int = None,
    edges: int = None
):
    """Update job progress and broadcast update."""
    job.progress = progress
    job.status = JobStatus.PROGRESS
    
    # Store progress data in job params so it's accessible via polling
    current_params = job.get_params()
    current_nodes = nodes if nodes is not None else (graph_service.graph.number_of_nodes() if graph_service.graph is not None else 0)
    current_edges = edges if edges is not None else (graph_service.graph.number_of_edges() if graph_service.graph is not None else 0)
    
    current_params['progress_data'] = {
        "nodes": current_nodes,
        "edges": current_edges,
        "message": message
    }
    job.set_params(current_params)
    
    session.add(job)
    session.commit()
    
    # Include node/edge counts in the update
    update_data = {
        "nodes": current_nodes,
        "edges": current_edges
    }
    
    # Log progress update
    if message:
        logger.debug(f"📊 Job {job_id}: {progress}% - {message} (Nodes: {current_nodes}, Edges: {current_edges})")
    
    await _broadcast_job_update(job_id, job.status, progress, message=message, data=update_data)


async def _broadcast_job_update(
    job_id: str,
    status: str,
    progress: int,
    result: dict = None,
    error: str = None,
    message: str = None,
    data: dict = None
):
    """Broadcast job update via event bus."""
    update_data = {
        "job_id": job_id,
        "status": status,
        "progress": progress
    }
    
    if result:
        update_data["result"] = result
    if error:
        update_data["error"] = error
    if message:
        update_data["message"] = message
    if data:
        update_data["data"] = data
    
    message_obj = {
        "type": "job.update",
        "data": update_data
    }
    
    # Publish to event bus
    await event_bus.publish_json("job_updates", message_obj)

