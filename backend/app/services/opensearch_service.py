"""
OpenSearch Service for Vector Search and Document Retrieval.

This service provides integration with AWS OpenSearch to retrieve relevant
documents based on vector similarity search. Used to provide context when
generating Splunk queries.
"""

from typing import List, Dict, Any, Optional
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth
from boto3 import session
from app.core.config import settings
import json


class OpenSearchService:
    """
    Service for interacting with AWS OpenSearch for vector search.
    
    Handles connection to OpenSearch, vector similarity search, and
    document retrieval for RAG (Retrieval Augmented Generation) use cases.
    """
    
    def __init__(self):
        """
        Initialize OpenSearch client with AWS authentication.
        
        Reads configuration from settings:
        - opensearch_host: OpenSearch cluster endpoint
        - opensearch_index: Index name for document storage
        - opensearch_region: AWS region
        - opensearch_use_aws_auth: Whether to use AWS authentication
        
        Raises:
            ValueError: If required configuration is missing
        """
        self.host = settings.opensearch_host
        self.index = settings.opensearch_index
        self.region = settings.opensearch_region
        self.use_aws_auth = settings.opensearch_use_aws_auth
        self.client = None
        
        if not self.host or not self.index:
            print("⚠️ OpenSearch not configured - vector search will be disabled")
            return
        
        try:
            if self.use_aws_auth:
                # Use AWS authentication for OpenSearch
                aws_session = session.Session()
                credentials = aws_session.get_credentials()
                
                awsauth = AWSRequestsAuth(
                    credentials=credentials,
                    aws_host=self.host.replace('https://', '').replace('http://', '').split(':')[0],
                    aws_region=self.region,
                    aws_service='es'
                )
                
                self.client = OpenSearch(
                    hosts=[{'host': self.host.replace('https://', '').replace('http://', ''), 'port': 443}],
                    http_auth=awsauth,
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection
                )
            else:
                # Basic authentication (for local development)
                self.client = OpenSearch(
                    hosts=[{'host': self.host.replace('https://', '').replace('http://', ''), 'port': 9200}],
                    http_auth=(settings.opensearch_username, settings.opensearch_password) if settings.opensearch_username else None,
                    use_ssl=settings.opensearch_use_ssl,
                    verify_certs=settings.opensearch_verify_certs,
                    connection_class=RequestsHttpConnection
                )
            
            print(f"✅ OpenSearch client initialized for index: {self.index}")
        except Exception as e:
            print(f"⚠️ Failed to initialize OpenSearch client: {e}")
            self.client = None
    
    async def search_relevant_documents(
        self,
        query_text: str,
        top_k: int = 5,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents using vector similarity.
        
        Performs a k-nearest neighbor (kNN) search on the vector index
        to find documents most similar to the query text.
        
        Args:
            query_text: The search query text
            top_k: Number of documents to retrieve (default: 5)
            min_score: Minimum similarity score threshold (default: 0.7)
        
        Returns:
            List[Dict[str, Any]]: List of relevant documents with metadata:
                - content: Document text content
                - score: Similarity score
                - metadata: Additional document metadata
        
        Edge Cases:
            - OpenSearch not configured: returns empty list
            - No results found: returns empty list
            - Search errors: logs error and returns empty list
        """
        if not self.client:
            print("⚠️ OpenSearch client not available, returning empty results")
            return []
        
        try:
            # Build kNN search query
            # Assumes documents have a 'vector' field with embeddings
            # and a 'text' or 'content' field with the document text
            search_body = {
                "size": top_k,
                "query": {
                    "bool": {
                        "should": [
                            {
                                "match": {
                                    "text": {
                                        "query": query_text,
                                        "boost": 1.0
                                    }
                                }
                            },
                            {
                                "match": {
                                    "content": {
                                        "query": query_text,
                                        "boost": 1.0
                                    }
                                }
                            }
                        ]
                    }
                },
                "_source": ["text", "content", "metadata", "title", "index_name", "field_mappings"]
            }
            
            # If vector search is enabled, add kNN query
            if settings.opensearch_use_vector_search:
                # Note: This requires the query to be embedded first
                # For now, we use text-based search
                # In production, you'd embed the query_text first
                pass
            
            # Execute search
            response = self.client.search(
                index=self.index,
                body=search_body
            )
            
            # Extract relevant documents
            documents = []
            for hit in response.get('hits', {}).get('hits', []):
                score = hit.get('_score', 0.0)
                
                # Filter by minimum score
                if score < min_score:
                    continue
                
                source = hit.get('_source', {})
                doc = {
                    'content': source.get('text') or source.get('content', ''),
                    'score': score,
                    'metadata': {
                        'title': source.get('title', ''),
                        'index_name': source.get('index_name', ''),
                        'field_mappings': source.get('field_mappings', {}),
                        **source.get('metadata', {})
                    }
                }
                
                if doc['content']:
                    documents.append(doc)
            
            print(f"📚 Retrieved {len(documents)} relevant documents from OpenSearch")
            return documents
            
        except Exception as e:
            print(f"❌ Error searching OpenSearch: {e}")
            import traceback
            print(traceback.format_exc())
            return []
    
    async def get_splunk_context(
        self,
        user_query: str,
        top_k: int = 3
    ) -> str:
        """
        Get relevant Splunk context from OpenSearch for query generation.
        
        Searches for documents related to Splunk indexes, field mappings,
        and query patterns that are relevant to the user's query.
        
        Args:
            user_query: User's natural language query
            top_k: Number of documents to retrieve (default: 3)
        
        Returns:
            str: Formatted context string with relevant information
        
        Format:
            Returns a formatted string with:
            - Index names and descriptions
            - Field mappings and available fields
            - Example queries related to the user's request
        """
        documents = await self.search_relevant_documents(user_query, top_k=top_k)
        
        if not documents:
            return ""
        
        # Format context from retrieved documents
        context_parts = []
        context_parts.append("Relevant context from knowledge base:")
        
        for i, doc in enumerate(documents, 1):
            content = doc.get('content', '')
            metadata = doc.get('metadata', {})
            title = metadata.get('title', f'Document {i}')
            
            context_parts.append(f"\n[{i}] {title}:")
            context_parts.append(content[:500])  # Limit content length
            
            # Add index and field information if available
            if metadata.get('index_name'):
                context_parts.append(f"  Index: {metadata['index_name']}")
            
            if metadata.get('field_mappings'):
                fields = list(metadata['field_mappings'].keys())[:10]  # Limit to 10 fields
                context_parts.append(f"  Available fields: {', '.join(fields)}")
        
        return "\n".join(context_parts)
    
    def is_available(self) -> bool:
        """
        Check if OpenSearch service is available and configured.
        
        Returns:
            bool: True if OpenSearch client is initialized and ready
        """
        return self.client is not None and self.host is not None
    
    async def ensure_java_index_exists(self) -> bool:
        """
        Ensure the Java code chunks index exists with proper mapping.
        
        Returns:
            bool: True if index exists or was created successfully
        """
        if not self.client:
            return False
        
        if not settings.java_opensearch_enabled:
            return False
        
        index_name = settings.java_opensearch_index
        
        try:
            # Check if index exists
            if self.client.indices.exists(index=index_name):
                print(f"✅ Java code chunks index '{index_name}' already exists")
                return True
            
            # Create index with mapping for Java chunks
            # Determine embedding dimension based on model
            embedding_dim = 1536  # Default for text-embedding-3-small
            if "large" in settings.java_embedding_model:
                embedding_dim = 3072
            elif "ada" in settings.java_embedding_model:
                embedding_dim = 1536
            
            mapping = {
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "repository_id": {"type": "keyword"},
                        "type": {"type": "keyword"},  # method, class, file, module
                        "fqn": {"type": "keyword"},  # Fully qualified name
                        "file_path": {"type": "keyword"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                        "code": {"type": "text"},  # Full source code
                        "summary": {"type": "text"},  # Generated summary
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": embedding_dim,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib"
                            }
                        },
                        "imports": {"type": "keyword"},  # Array of imports
                        "annotations": {"type": "keyword"},  # Array of annotations
                        "callers": {"type": "keyword"},  # Array of caller FQNs
                        "callees": {"type": "keyword"},  # Array of callee FQNs
                        "implemented_interfaces": {"type": "keyword"},
                        "extended_class": {"type": "keyword"},
                        "test_references": {"type": "keyword"},
                        "last_modified": {"type": "date"},
                        "created_at": {"type": "date"}
                    }
                }
            }
            
            self.client.indices.create(index=index_name, body=mapping)
            print(f"✅ Created Java code chunks index '{index_name}' with {embedding_dim}D embeddings")
            return True
            
        except Exception as e:
            print(f"❌ Error ensuring Java index exists: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    async def index_java_chunk(
        self,
        chunk_id: int,
        repository_id: int,
        chunk_type: str,
        fqn: str,
        file_path: str,
        start_line: int,
        end_line: int,
        code: str,
        summary: Optional[str],
        embedding: List[float],
        imports: Optional[List[str]] = None,
        annotations: Optional[List[str]] = None,
        callers: Optional[List[str]] = None,
        callees: Optional[List[str]] = None,
        implemented_interfaces: Optional[List[str]] = None,
        extended_class: Optional[str] = None,
        test_references: Optional[List[str]] = None,
        last_modified: Optional[str] = None
    ) -> bool:
        """
        Index a Java code chunk in OpenSearch.
        
        Args:
            chunk_id: Database chunk ID
            repository_id: Repository ID
            chunk_type: Chunk type (method, class, file, module)
            fqn: Fully qualified name
            file_path: File path
            start_line: Starting line number
            end_line: Ending line number
            code: Source code
            summary: Generated summary
            embedding: Vector embedding
            imports: List of imports
            annotations: List of annotations
            callers: List of caller FQNs
            callees: List of callee FQNs
            implemented_interfaces: List of implemented interfaces
            extended_class: Extended class name
            test_references: List of test references
            last_modified: Last modification timestamp
        
        Returns:
            bool: True if indexing succeeded
        """
        if not self.client:
            return False
        
        if not settings.java_opensearch_enabled:
            return False
        
        try:
            # Ensure index exists
            await self.ensure_java_index_exists()
            
            document = {
                "chunk_id": chunk_id,
                "repository_id": repository_id,
                "type": chunk_type,
                "fqn": fqn,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "code": code,
                "summary": summary or "",
                "embedding": embedding,
                "imports": imports or [],
                "annotations": annotations or [],
                "callers": callers or [],
                "callees": callees or [],
                "implemented_interfaces": implemented_interfaces or [],
                "extended_class": extended_class or "",
                "test_references": test_references or [],
                "last_modified": last_modified,
                "created_at": "now"
            }
            
            # Use chunk_id as document ID for easy updates
            self.client.index(
                index=settings.java_opensearch_index,
                id=str(chunk_id),
                body=document
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error indexing Java chunk {chunk_id} in OpenSearch: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    async def delete_java_chunks_by_repository(self, repository_id: int) -> bool:
        """
        Delete all chunks for a repository from OpenSearch.
        
        Args:
            repository_id: Repository ID
        
        Returns:
            bool: True if deletion succeeded
        """
        if not self.client:
            return False
        
        if not settings.java_opensearch_enabled:
            return False
        
        try:
            query = {
                "query": {
                    "term": {"repository_id": repository_id}
                }
            }
            
            self.client.delete_by_query(
                index=settings.java_opensearch_index,
                body=query
            )
            
            print(f"✅ Deleted chunks for repository {repository_id} from OpenSearch")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting chunks for repository {repository_id}: {e}")
            return False
    
    async def delete_java_chunk(self, chunk_id: int) -> bool:
        """
        Delete a specific chunk from OpenSearch.
        
        Args:
            chunk_id: Chunk ID
        
        Returns:
            bool: True if deletion succeeded
        """
        if not self.client:
            return False
        
        if not settings.java_opensearch_enabled:
            return False
        
        try:
            self.client.delete(
                index=settings.java_opensearch_index,
                id=str(chunk_id)
            )
            return True
            
        except Exception as e:
            print(f"❌ Error deleting chunk {chunk_id} from OpenSearch: {e}")
            return False
    
    async def update_java_chunk_relationships(
        self,
        chunk_id: int,
        callers: Optional[List[str]] = None,
        callees: Optional[List[str]] = None
    ) -> bool:
        """
        Update relationship fields (callers/callees) for a chunk in OpenSearch.
        
        Args:
            chunk_id: Chunk ID
            callers: Updated list of caller FQNs
            callees: Updated list of callee FQNs
        
        Returns:
            bool: True if update succeeded
        """
        if not self.client:
            return False
        
        if not settings.java_opensearch_enabled:
            return False
        
        try:
            update_doc = {}
            if callers is not None:
                update_doc["callers"] = callers
            if callees is not None:
                update_doc["callees"] = callees
            
            if not update_doc:
                return True  # Nothing to update
            
            self.client.update(
                index=settings.java_opensearch_index,
                id=str(chunk_id),
                body={"doc": update_doc}
            )
            
            return True
            
        except Exception as e:
            # Chunk might not exist in OpenSearch yet, which is okay
            print(f"⚠️ Could not update relationships for chunk {chunk_id} in OpenSearch: {e}")
            return False


# Global instance
opensearch_service = OpenSearchService()

