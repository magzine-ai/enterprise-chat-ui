"""
Graph Service for building and querying code knowledge graphs.

Uses NetworkX for fast in-memory graph operations and optionally
TigerGraph for large-scale graph operations.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
import logging
import os
import pickle
from pathlib import Path
from sqlmodel import Session, select
from app.models.java_chunk import JavaChunk
from app.models.java_repository import JavaRepository

logger = logging.getLogger(__name__)

# Try to import NetworkX
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    logger.warning("networkx not installed. Graph operations will be limited.")

# Try to import TigerGraph (optional)
try:
    from pyTigerGraph import TigerGraphConnection
    TIGERGRAPH_AVAILABLE = True
except ImportError:
    TIGERGRAPH_AVAILABLE = False
    logger.info("TigerGraph not installed. Using NetworkX only.")


class GraphService:
    """
    Service for building and querying code knowledge graphs.
    
    Features:
    - NetworkX for fast in-memory graph operations
    - Optional TigerGraph for large-scale graphs
    - Relationship types: calls, imports, extends, implements, depends_on
    - Cross-repository relationship tracking
    """
    
    def __init__(self, graph_storage_path: Optional[str] = None):
        """
        Initialize graph service.
        
        Args:
            graph_storage_path: Optional path to directory for storing graph files.
                              Defaults to 'data/graphs' in the backend directory.
        """
        self.graph = None
        self.tigergraph_conn = None
        
        # Set up graph storage path
        if graph_storage_path:
            self.graph_storage_path = Path(graph_storage_path)
        else:
            # Default to data/graphs in backend directory
            backend_dir = Path(__file__).parent.parent.parent
            self.graph_storage_path = backend_dir / "data" / "graphs"
        
        # Create storage directory if it doesn't exist
        self.graph_storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Graph storage path: {self.graph_storage_path}")
        
        if NETWORKX_AVAILABLE:
            self.graph = nx.MultiDiGraph()  # Directed graph with multiple edges
            logger.info("✅ NetworkX graph initialized")
        else:
            logger.warning("⚠️ NetworkX not available, graph operations disabled")
    
    def build_graph_from_chunks(
        self,
        session: Session,
        repository_id: Optional[int] = None,
        rebuild: bool = False
    ) -> bool:
        """
        Build knowledge graph from code chunks.
        
        Args:
            session: Database session
            repository_id: Optional repository filter
            rebuild: If True and repository_id is provided, clear only that repository's nodes before rebuilding
        
        Returns:
            True if successful, False otherwise
        """
        # Ensure graph is initialized
        if self.graph is None:
            if NETWORKX_AVAILABLE:
                try:
                    self.graph = nx.MultiDiGraph()
                    logger.info("Graph initialized in build_graph_from_chunks")
                except Exception as e:
                    logger.error(f"Failed to initialize graph: {e}")
                    return False
            else:
                logger.error("NetworkX not available. Install with: pip install networkx")
                return False
        
        try:
            # Clear graph: either specific repository (if rebuild) or entire graph
            if rebuild and repository_id is not None:
                # Clear only this repository's nodes/edges
                self.clear_repository_graph(repository_id)
                logger.info(f"Cleared existing graph for repository {repository_id} before rebuild")
            else:
                # Clear entire graph (original behavior for backward compatibility)
                self.graph.clear()
            
            # Get all chunks
            query = select(JavaChunk)
            if repository_id:
                query = query.where(JavaChunk.repository_id == repository_id)
            
            chunks = session.exec(query).all()
            
            if not chunks:
                logger.warning(f"No chunks found for repository {repository_id}")
                return False
            
            logger.info(f"Building graph from {len(chunks)} chunks for repository {repository_id}")
            
            # Add all chunks as nodes
            nodes_added = 0
            for chunk in chunks:
                node_id = f"chunk_{chunk.id}"
                self.graph.add_node(
                    node_id,
                    type=chunk.type,
                    fqn=chunk.fqn,
                    repository_id=chunk.repository_id,
                    file_path=chunk.file_path,
                    chunk_id=chunk.id,
                )
                nodes_added += 1
            
            logger.info(f"Added {nodes_added} nodes to graph")
            
            # Add intra-repository edges (callers/callees)
            edges_added = 0
            method_chunks = [c for c in chunks if c.type == "method"]
            logger.info(f"Processing {len(method_chunks)} method chunks for edges")
            
            for chunk in method_chunks:
                node_id = f"chunk_{chunk.id}"
                callers = chunk.get_callers()
                callees = chunk.get_callees()
                
                # Add caller edges (reverse direction)
                for caller_fqn in callers:
                    try:
                        caller_chunk = self._find_chunk_by_fqn(session, caller_fqn, chunk.repository_id)
                        if caller_chunk:
                            caller_node_id = f"chunk_{caller_chunk.id}"
                            self.graph.add_edge(
                                caller_node_id, node_id,
                                relationship='calls',
                                type='caller'
                            )
                            edges_added += 1
                    except Exception as e:
                        logger.debug(f"Error adding caller edge for {caller_fqn}: {e}")
                
                # Add callee edges
                for callee_fqn in callees:
                    try:
                        callee_chunk = self._find_chunk_by_fqn(session, callee_fqn, chunk.repository_id)
                        if callee_chunk:
                            callee_node_id = f"chunk_{callee_chunk.id}"
                            self.graph.add_edge(
                                node_id, callee_node_id,
                                relationship='calls',
                                type='callee'
                            )
                            edges_added += 1
                    except Exception as e:
                        logger.debug(f"Error adding callee edge for {callee_fqn}: {e}")
                
                # Add import edges
                imports = chunk.get_imports()
                for imp in imports:
                    try:
                        # Try to find chunks that match this import
                        imported_chunk = self._find_chunk_by_import(session, imp, chunk.repository_id)
                        if imported_chunk:
                            imported_node_id = f"chunk_{imported_chunk.id}"
                            self.graph.add_edge(
                                node_id, imported_node_id,
                                relationship='imports',
                                type='import',
                                import_name=imp
                            )
                            edges_added += 1
                    except Exception as e:
                        logger.debug(f"Error adding import edge for {imp}: {e}")
            
            final_nodes = self.graph.number_of_nodes()
            final_edges = self.graph.number_of_edges()
            logger.info(f"✅ Graph built: {final_nodes} nodes, {final_edges} edges (added {edges_added} edges)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to build graph: {e}")
            return False
    
    def _find_chunk_by_fqn(
        self,
        session: Session,
        fqn: str,
        repository_id: int
    ) -> Optional[JavaChunk]:
        """Find chunk by FQN in a repository."""
        return session.exec(
            select(JavaChunk).where(
                JavaChunk.fqn == fqn,
                JavaChunk.repository_id == repository_id
            )
        ).first()
    
    def _find_chunk_by_import(
        self,
        session: Session,
        import_name: str,
        repository_id: int
    ) -> Optional[JavaChunk]:
        """Find chunk that matches an import."""
        # Try to match by FQN containing the import
        # Extract class name from import
        class_name = import_name.split('.')[-1] if '.' in import_name else import_name
        
        # Search for chunks with matching class name
        chunks = session.exec(
            select(JavaChunk).where(
                JavaChunk.fqn.contains(class_name),
                JavaChunk.repository_id == repository_id,
                JavaChunk.type == "class"
            )
        ).limit(1).all()
        
        return chunks[0] if chunks else None
    
    async def find_related_code(
        self,
        session: Session,
        chunk_id: int,
        max_depth: int = 2,
        include_cross_repo: bool = True,
        relationship_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find related code using graph traversal.
        
        Args:
            session: Database session
            chunk_id: Starting chunk ID
            max_depth: Maximum traversal depth
            include_cross_repo: Whether to include cross-repository relationships
            relationship_types: Optional list of relationship types to follow
        
        Returns:
            List of related code chunks
        """
        if self.graph is None:
            logger.warning("Graph not initialized")
            return []
        
        node_id = f"chunk_{chunk_id}"
        if node_id not in self.graph:
            logger.warning(f"Node {node_id} not found in graph")
            return []
        
        related = []
        visited = set()
        queue = [(node_id, 0)]  # (node_id, depth)
        
        if relationship_types is None:
            relationship_types = ['calls', 'imports', 'extends', 'implements']
        
        while queue:
            current_node, depth = queue.pop(0)
            
            if depth > max_depth or current_node in visited:
                continue
            
            visited.add(current_node)
            
            # Get neighbors in both directions (successors and predecessors)
            neighbors = list(self.graph.successors(current_node)) + list(self.graph.predecessors(current_node))
            
            for neighbor_id in neighbors:
                if neighbor_id in visited:
                    continue
                
                # Determine direction and get edge data
                edge_data = None
                direction = None
                
                # Check outgoing edge (current -> neighbor)
                edge_data = self.graph.get_edge_data(current_node, neighbor_id)
                if edge_data:
                    direction = 'outgoing'
                else:
                    # Check incoming edge (neighbor -> current)
                    edge_data = self.graph.get_edge_data(neighbor_id, current_node)
                    if edge_data:
                        direction = 'incoming'
                
                if not edge_data:
                    continue
                
                # Check relationship type
                rel_type = None
                for edge_key, edge_info in edge_data.items():
                    if edge_info.get('relationship') in relationship_types:
                        rel_type = edge_info.get('relationship')
                        break
                
                if not rel_type:
                    continue
                
                # Check if cross-repository
                current_repo = self.graph.nodes[current_node].get('repository_id')
                neighbor_repo = self.graph.nodes[neighbor_id].get('repository_id')
                is_cross_repo = current_repo != neighbor_repo
                
                if include_cross_repo or not is_cross_repo:
                    neighbor_chunk_id = self.graph.nodes[neighbor_id].get('chunk_id')
                    if neighbor_chunk_id:
                        neighbor_chunk = session.get(JavaChunk, neighbor_chunk_id)
                        if neighbor_chunk:
                            related.append({
                                'chunk_id': neighbor_chunk_id,
                                'fqn': neighbor_chunk.fqn,
                                'file_path': neighbor_chunk.file_path,
                                'depth': depth + 1,
                                'cross_repository': is_cross_repo,
                                'relationship': rel_type,
                                'direction': direction
                            })
                            queue.append((neighbor_id, depth + 1))
        
        return related
    
    async def get_call_graph(
        self,
        session: Session,
        function_fqn: str,
        repository_id: Optional[int] = None,
        direction: str = "both"  # "forward", "backward", "both"
    ) -> Dict[str, Any]:
        """
        Get call graph for a function.
        
        Args:
            session: Database session
            function_fqn: Function FQN
            repository_id: Optional repository filter
            direction: Traversal direction
        
        Returns:
            Dict with call graph information
        """
        if self.graph is None:
            return {"functions": [], "edges": []}
        
        # Find starting chunk
        query = select(JavaChunk).where(JavaChunk.fqn == function_fqn)
        if repository_id:
            query = query.where(JavaChunk.repository_id == repository_id)
        
        start_chunk = session.exec(query).first()
        if not start_chunk:
            return {"functions": [], "edges": []}
        
        start_node = f"chunk_{start_chunk.id}"
        if start_node not in self.graph:
            return {"functions": [], "edges": []}
        
        functions = []
        edges = []
        visited = set()
        
        def traverse(node_id: str, depth: int = 0, max_depth: int = 3):
            if depth > max_depth or node_id in visited:
                return
            
            visited.add(node_id)
            node_data = self.graph.nodes[node_id]
            chunk_id = node_data.get('chunk_id')
            
            if chunk_id:
                chunk = session.get(JavaChunk, chunk_id)
                if chunk:
                    functions.append({
                        'fqn': chunk.fqn,
                        'file_path': chunk.file_path,
                        'start_line': chunk.start_line,
                        'end_line': chunk.end_line,
                    })
            
            # Traverse edges
            if direction in ["forward", "both"]:
                for successor in self.graph.successors(node_id):
                    edge_data = self.graph.get_edge_data(node_id, successor)
                    for edge_key, edge_info in edge_data.items():
                        if edge_info.get('relationship') == 'calls':
                            edges.append({
                                'from': node_data.get('fqn'),
                                'to': self.graph.nodes[successor].get('fqn'),
                                'type': 'calls'
                            })
                            traverse(successor, depth + 1, max_depth)
            
            if direction in ["backward", "both"]:
                for predecessor in self.graph.predecessors(node_id):
                    edge_data = self.graph.get_edge_data(predecessor, node_id)
                    for edge_key, edge_info in edge_data.items():
                        if edge_info.get('relationship') == 'calls':
                            edges.append({
                                'from': self.graph.nodes[predecessor].get('fqn'),
                                'to': node_data.get('fqn'),
                                'type': 'called_by'
                            })
                            traverse(predecessor, depth + 1, max_depth)
        
        traverse(start_node)
        
        return {
            "functions": functions,
            "edges": edges,
        }
    
    async def get_file_dependencies(
        self,
        session: Session,
        file_path: str,
        repository_id: Optional[int] = None,
        depth: int = 2
    ) -> Dict[str, Any]:
        """
        Get file dependencies.
        
        Args:
            session: Database session
            file_path: File path
            repository_id: Optional repository filter
            depth: Traversal depth
        
        Returns:
            Dict with file dependencies
        """
        if self.graph is None:
            return {"files": [], "dependencies": []}
        
        # Find chunks in this file
        query = select(JavaChunk).where(JavaChunk.file_path == file_path)
        if repository_id:
            query = query.where(JavaChunk.repository_id == repository_id)
        
        file_chunks = session.exec(query).all()
        if not file_chunks:
            return {"files": [], "dependencies": []}
        
        dependencies = []
        visited_files = set()
        
        for chunk in file_chunks:
            node_id = f"chunk_{chunk.id}"
            if node_id not in self.graph:
                continue
            
            # Find imported files
            for successor in self.graph.successors(node_id):
                edge_data = self.graph.get_edge_data(node_id, successor)
                for edge_key, edge_info in edge_data.items():
                    if edge_info.get('relationship') == 'imports':
                        dep_file = self.graph.nodes[successor].get('file_path')
                        if dep_file and dep_file not in visited_files:
                            visited_files.add(dep_file)
                            dependencies.append({
                                'path': dep_file,
                                'type': 'import',
                            })
        
        return {
            "files": [{'path': file_path}],
            "dependencies": dependencies,
        }
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Get graph statistics.
        
        Returns:
            Dict with graph statistics
        """
        if self.graph is None:
            return {
                "nodes": 0,
                "edges": 0,
                "available": False
            }
        
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "available": True
        }
    
    def clear_graph(self):
        """Clear the graph."""
        if self.graph:
            self.graph.clear()
            logger.info("Graph cleared")
    
    def clear_repository_graph(self, repository_id: int):
        """
        Clear nodes and edges for a specific repository.
        
        Args:
            repository_id: Repository ID to clear
        """
        if self.graph is None:
            return
        
        # Find all nodes for this repository
        nodes_to_remove = [
            node for node, data in self.graph.nodes(data=True)
            if data.get('repository_id') == repository_id
        ]
        
        # Remove nodes (this will also remove connected edges)
        self.graph.remove_nodes_from(nodes_to_remove)
        
        logger.info(f"Cleared {len(nodes_to_remove)} nodes for repository {repository_id}")
    
    def get_graph_file_path(self, repository_id: Optional[int] = None) -> Path:
        """
        Get the file path for storing/loading a graph.
        
        Args:
            repository_id: Optional repository ID. If None, uses 'global' graph.
        
        Returns:
            Path to graph file
        """
        if repository_id:
            filename = f"graph_repo_{repository_id}.pkl"
        else:
            filename = "graph_global.pkl"
        return self.graph_storage_path / filename
    
    def save_graph(self, repository_id: Optional[int] = None) -> bool:
        """
        Save the current graph to disk.
        
        Args:
            repository_id: Optional repository ID to save graph for specific repository.
                          If None, saves the global graph.
        
        Returns:
            True if successful, False otherwise
        """
        if self.graph is None:
            logger.warning("Cannot save graph: graph is not initialized")
            return False
        
        try:
            graph_file = self.get_graph_file_path(repository_id)
            
            # Save graph using pickle
            with open(graph_file, 'wb') as f:
                pickle.dump(self.graph, f)
            
            node_count = self.graph.number_of_nodes()
            edge_count = self.graph.number_of_edges()
            logger.info(f"💾 Saved graph to {graph_file} ({node_count} nodes, {edge_count} edges)")
            return True
        except Exception as e:
            logger.error(f"Failed to save graph: {e}", exc_info=True)
            return False
    
    def load_graph(self, repository_id: Optional[int] = None) -> bool:
        """
        Load graph from disk.
        
        Args:
            repository_id: Optional repository ID to load graph for specific repository.
                          If None, loads the global graph.
        
        Returns:
            True if successful, False otherwise
        """
        if not NETWORKX_AVAILABLE:
            logger.warning("Cannot load graph: NetworkX not available")
            return False
        
        try:
            graph_file = self.get_graph_file_path(repository_id)
            
            if not graph_file.exists():
                logger.info(f"Graph file not found: {graph_file}")
                return False
            
            # Load graph from pickle
            with open(graph_file, 'rb') as f:
                loaded_graph = pickle.load(f)
            
            # Validate it's a NetworkX graph
            if not isinstance(loaded_graph, nx.MultiDiGraph):
                logger.error(f"Invalid graph format in {graph_file}")
                return False
            
            self.graph = loaded_graph
            node_count = self.graph.number_of_nodes()
            edge_count = self.graph.number_of_edges()
            logger.info(f"📂 Loaded graph from {graph_file} ({node_count} nodes, {edge_count} edges)")
            return True
        except Exception as e:
            logger.error(f"Failed to load graph: {e}", exc_info=True)
            return False
    
    def graph_exists(self, repository_id: Optional[int] = None) -> bool:
        """
        Check if a graph file exists for the given repository.
        
        Args:
            repository_id: Optional repository ID. If None, checks for global graph.
        
        Returns:
            True if graph file exists, False otherwise
        """
        graph_file = self.get_graph_file_path(repository_id)
        return graph_file.exists()
    
    def search_nodes_by_query(
        self,
        query: str,
        repository_id: Optional[int] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search graph nodes by query string (FQN, name, file path).
        
        Args:
            query: Search query (searches in FQN, file_path)
            repository_id: Optional repository filter
            max_results: Maximum number of results
        
        Returns:
            List of matching nodes with their data
        """
        if self.graph is None:
            logger.warning("Graph not initialized for node search")
            return []
        
        query_lower = query.lower()
        results = []
        
        for node_id, node_data in self.graph.nodes(data=True):
            # Skip if repository filter doesn't match
            if repository_id is not None and node_data.get('repository_id') != repository_id:
                continue
            
            # Search in FQN
            fqn = node_data.get('fqn', '')
            if query_lower in fqn.lower():
                results.append({
                    'node_id': node_id,
                    'chunk_id': node_data.get('chunk_id'),
                    'fqn': fqn,
                    'file_path': node_data.get('file_path', ''),
                    'type': node_data.get('type', 'unknown'),
                    'repository_id': node_data.get('repository_id'),
                    'match_type': 'fqn'
                })
                if len(results) >= max_results:
                    break
            
            # Also search in file path if not already found
            if len(results) < max_results:
                file_path = node_data.get('file_path', '')
                if query_lower in file_path.lower() and not any(r['chunk_id'] == node_data.get('chunk_id') for r in results):
                    results.append({
                        'node_id': node_id,
                        'chunk_id': node_data.get('chunk_id'),
                        'fqn': fqn,
                        'file_path': file_path,
                        'type': node_data.get('type', 'unknown'),
                        'repository_id': node_data.get('repository_id'),
                        'match_type': 'file_path'
                    })
                    if len(results) >= max_results:
                        break
        
        # Sort by relevance (exact FQN matches first, then partial)
        results.sort(key=lambda x: (
            0 if query_lower == x['fqn'].lower() else 1,  # Exact match first
            0 if x['fqn'].lower().startswith(query_lower) else 1,  # Starts with query
            len(x['fqn'])  # Shorter FQNs first
        ))
        
        logger.info(f"Found {len(results)} graph nodes matching query '{query}'")
        return results[:max_results]


# Global instance
graph_service = GraphService()

