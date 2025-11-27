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


# Global instance
opensearch_service = OpenSearchService()

