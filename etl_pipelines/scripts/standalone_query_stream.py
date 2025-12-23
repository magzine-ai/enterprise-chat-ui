"""
Standalone script to query OpenSearch, load graph, and generate streaming LLM responses.
No dependencies on project structure.

Usage:
  python standalone_query_stream.py \
    --query "who calls startDemo" \
    --opensearch-host search-domain.us-east-1.es.amazonaws.com \
    --opensearch-index code_chunks \
    --graph-file ./output/graph.pkl \
    --use-azure-embeddings \
    --use-llm

Requirements:
  pip install opensearch-py networkx aws-requests-auth boto3 langchain-openai azure-identity
"""

import argparse
import pickle
import os
import sys
import configparser
from pathlib import Path
from typing import List, Dict, Any, Optional

# OpenSearch
try:
    from opensearchpy import OpenSearch, RequestsHttpConnection
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False
    print("⚠️ OpenSearch not available. Install: pip install opensearch-py")

# AWS Authentication for OpenSearch
try:
    from aws_requests_auth.aws_auth import AWSRequestsAuth
    from boto3 import session
    AWS_AUTH_AVAILABLE = True
except ImportError:
    AWS_AUTH_AVAILABLE = False
    print("⚠️ AWS authentication not available. Install: pip install aws-requests-auth boto3")

# NetworkX for graph
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    print("⚠️ NetworkX not available. Install: pip install networkx")

# Azure OpenAI for Embeddings
try:
    from azure.identity import CertificateCredential
    from azure.core.exceptions import ClientAuthenticationError
    from langchain_openai import AzureOpenAIEmbeddings
    AZURE_EMBEDDINGS_AVAILABLE = True
except ImportError:
    AZURE_EMBEDDINGS_AVAILABLE = False
    print("⚠️ Azure embeddings not available. Install: pip install azure-identity langchain-openai")

# Azure OpenAI for LLM (chat client)
try:
    from langchain_openai import AzureChatOpenAI
    AZURE_LLM_AVAILABLE = True
except ImportError:
    AZURE_LLM_AVAILABLE = False
    print("⚠️ Azure LLM not available. Install: pip install langchain-openai azure-identity")


class EmbeddingService:
    """Azure OpenAI Embedding Service with certificate-based authentication."""
    
    def __init__(self, user_sid: str = "default_user", cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """Initialize the embedding service."""
        self.config = self.load_config(config_path)
        self.user_sid = user_sid
        self.access_token = self.get_access_token(cert_path, config_path)
        if self.access_token:
            print(f"✅ EmbeddingService access token obtained")
        self.embeddings = self.create_embeddings_client()
    
    @staticmethod
    def load_config(config_path: Optional[str] = None):
        """Load configuration from config.ini file."""
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            file_path = os.path.join(current_dir, 'config.ini')
        else:
            file_path = config_path
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        llm_config = configparser.ConfigParser()
        llm_config.read(file_path)
        return llm_config
    
    @staticmethod
    def get_access_token(cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """Obtain access token using certificate-based authentication."""
        config = EmbeddingService.load_config(config_path)
        current_dir = os.path.dirname(__file__)
        
        try:
            if cert_path is None:
                cert_path = os.path.join(current_dir, "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem")
            
            if not os.path.exists(cert_path):
                alt_paths = [
                    os.path.join(current_dir, "discoveryeng.dev.azure.jpmchase.net.pem"),
                    os.path.join(os.path.dirname(current_dir), "discoveryeng.dev.azure.jpmchase.net.pem"),
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        cert_path = alt_path
                        break
                else:
                    raise FileNotFoundError(f"Certificate file not found: {cert_path}")
            
            credential = CertificateCredential(
                tenant_id=config['azure_openai']['azure_tenant_id'],
                client_id=config['azure_openai']['azure_client_id'],
                certificate_path=cert_path
            )
            
            access_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
            return access_token
        except ClientAuthenticationError as e:
            print(f"Authentication failed: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None
    
    def create_embeddings_client(self):
        """Create Azure OpenAI Embeddings client."""
        if not self.access_token:
            raise Exception("No access token available for Azure OpenAI Embeddings.")
        
        return AzureOpenAIEmbeddings(
            azure_endpoint="https://llm-multitenancy-exp.jpmchase.net/ver2/",
            openai_api_version="2024-10-21",
            openai_api_key="b3d265714de0417cbd8af5c26b6013b1",
            openai_api_type="azure",
            default_headers={
                "Authorization": f"Bearer {self.access_token}",
                "user_sid": self.user_sid
            }
        )
    
    def embed_text(self, text: str) -> List[float]:
        """Embed a single string using AzureOpenAIEmbeddings."""
        return self.embeddings.embed_query(text)


class TokenManager:
    """Manages Azure OpenAI access tokens with certificate-based authentication."""
    
    def __init__(self, cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """Initialize token manager."""
        self.config = self._load_config(config_path)
        self.cert_path = cert_path
        self.config_path = config_path
        self.access_token = None
        self._refresh_token()
    
    @staticmethod
    def _load_config(config_path: Optional[str] = None):
        """Load configuration from config.ini file."""
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            file_path = os.path.join(current_dir, 'config.ini')
        else:
            file_path = config_path
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        config = configparser.ConfigParser()
        config.read(file_path)
        return config
    
    def _refresh_token(self):
        """Refresh the access token."""
        current_dir = os.path.dirname(__file__)
        
        try:
            if self.cert_path is None:
                self.cert_path = os.path.join(current_dir, "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem")
            
            if not os.path.exists(self.cert_path):
                alt_paths = [
                    os.path.join(current_dir, "discoveryeng.dev.azure.jpmchase.net.pem"),
                    os.path.join(os.path.dirname(current_dir), "discoveryeng.dev.azure.jpmchase.net.pem"),
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        self.cert_path = alt_path
                        break
                else:
                    raise FileNotFoundError(f"Certificate file not found: {self.cert_path}")
            
            credential = CertificateCredential(
                tenant_id=self.config['azure_openai']['azure_tenant_id'],
                client_id=self.config['azure_openai']['azure_client_id'],
                certificate_path=self.cert_path
            )
            
            self.access_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
        except ClientAuthenticationError as e:
            print(f"Authentication failed: {e}")
            self.access_token = None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            self.access_token = None
    
    def get_token(self) -> Optional[str]:
        """Get current access token, refreshing if needed."""
        if not self.access_token:
            self._refresh_token()
        return self.access_token


class LLMClient:
    """Azure OpenAI LLM client with streaming support."""
    
    def __init__(
        self,
        token_manager: Optional[TokenManager] = None,
        user_sid: str = "default_user",
        cert_path: Optional[str] = None,
        config_path: Optional[str] = None
    ):
        """Initialize LLM client."""
        if not AZURE_LLM_AVAILABLE:
            self.chat_client = None
            print("⚠️ Azure LLM not available")
            return
        
        if token_manager is None:
            token_manager = TokenManager(cert_path=cert_path, config_path=config_path)
        
        self.token_manager = token_manager
        self.user_sid = user_sid
        self.config = token_manager.config if token_manager else None
        
        if not self.config or 'azure_openai' not in self.config:
            print("⚠️ Azure OpenAI config not found")
            self.chat_client = None
            return
        
        self._refresh_client()
    
    def _refresh_client(self):
        """Refresh the chat client with latest token."""
        if not self.token_manager:
            return
        
        access_token = self.token_manager.get_token()
        if not access_token:
            print("⚠️ No access token available")
            self.chat_client = None
            return
        
        try:
            azure_endpoint = self.config['azure_openai'].get('azure_endpoint', 'https://llm-multitenancy-exp.jpmchase.net/ver2/')
            openai_api_key = self.config['azure_openai'].get('openai_api_key', 'b3d265714de0417cbd8af5c26b6013b1')
            
            self.chat_client = AzureChatOpenAI(
                azure_endpoint=azure_endpoint,
                openai_api_version=self.config['azure_openai'].get('openai_api_version', '2024-10-21'),
                deployment_name=self.config['azure_openai'].get('deployment_name', 'gpt-4'),
                openai_api_key=openai_api_key,
                openai_api_type="azure",
                max_tokens=int(self.config['azure_openai'].get('max_tokens', '2000')),
                temperature=float(self.config['azure_openai'].get('temperature', '0.7')),
                streaming=True,
                default_headers={
                    "Authorization": f"Bearer {access_token}",
                    "user_sid": self.user_sid
                }
            )
            print("✅ LLM client initialized")
        except Exception as e:
            print(f"⚠️ Failed to initialize LLM client: {e}")
            self.chat_client = None
    
    def get_chat_client(self):
        """Get chat client with latest token."""
        if self.chat_client and self.token_manager:
            access_token = self.token_manager.get_token()
            if access_token:
                self.chat_client.default_headers["Authorization"] = f"Bearer {access_token}"
        return self.chat_client
    
    def generate_response_stream(
        self,
        query: str,
        context: List[Dict[str, Any]],
        graph_context: Optional[str] = None
    ):
        """
        Generate streaming LLM response with context from search results and graph.
        
        Args:
            query: User query
            context: List of search results to use as context
            graph_context: Optional graph information as string
        
        Yields:
            Response chunks as they are generated
        """
        if not self.chat_client:
            yield "LLM client not available. Please check configuration."
            return
        
        # Build context from search results
        context_text = "Relevant code snippets from the codebase:\n\n"
        for i, result in enumerate(context[:5], 1):  # Use top 5 results
            context_text += f"--- Result {i} ---\n"
            context_text += f"File: {result.get('file_path', 'unknown')}\n"
            context_text += f"Type: {result.get('type', 'unknown')}\n"
            context_text += f"FQN: {result.get('fqn', 'unknown')}\n"
            if result.get('module'):
                context_text += f"Module: {result.get('module')}\n"
            context_text += f"Code:\n{result.get('code', '')[:500]}\n\n"  # Limit code length
        
        # Add graph context if available
        if graph_context:
            context_text += f"\n--- Graph Relationships ---\n{graph_context}\n\n"
        
        # Build prompt
        prompt = f"""You are a helpful code assistant. Answer the user's question based on the provided code context.

Context:
{context_text}

User Question: {query}

Please provide a clear and concise answer based on the code context provided. If the context doesn't contain enough information, say so."""
        
        try:
            client = self.get_chat_client()
            if not client:
                yield "Failed to get LLM client"
                return
            
            # Stream response
            for chunk in client.stream(prompt):
                if hasattr(chunk, 'content') and chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"Error generating response: {str(e)}"


class StandaloneSearcher:
    """Self-contained OpenSearch searcher with AWS authentication support."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        index: Optional[str] = None,
        config_path: Optional[str] = None,
        use_aws_auth: bool = True,
        region: Optional[str] = None,
        use_ssl: bool = True,
        verify_certs: bool = True,
        use_azure_embeddings: bool = False,
        user_sid: str = "default_user",
        azure_cert_path: Optional[str] = None,
        azure_config_path: Optional[str] = None
    ):
        """Initialize OpenSearch searcher."""
        self.host = host
        self.index = index
        self.client = None
        self.azure_embedding_service = None
        
        # Store AWS auth configuration for token refresh
        self.use_aws_auth = use_aws_auth
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self.aws_session = None
        self.aws_host = None
        self.hostname = None
        self.port = None
        
        # Load config
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            config_path = os.path.join(current_dir, "config.ini")
        
        if os.path.exists(config_path):
            self.config = configparser.ConfigParser()
            self.config.read(config_path)
            
            # Extract OpenSearch config from config file
            if 'aws_info' in self.config:
                self.opensearch_endpoint = self.config['aws_info'].get('opensearch_endpoint', host or '')
                self.index_name = self.config['aws_info'].get('index_name', index or 'code_chunks')
                self.region = self.config['aws_info'].get('region', region or 'us-east-1')
            else:
                self.opensearch_endpoint = host or ''
                self.index_name = index or 'code_chunks'
                self.region = region or 'us-east-1'
        else:
            self.opensearch_endpoint = host or ''
            self.index_name = index or 'code_chunks'
            self.region = region or 'us-east-1'
            self.config = None
        
        if not self.opensearch_endpoint:
            print("⚠️ OpenSearch endpoint not provided and not found in config")
            return
        
        if not OPENSEARCH_AVAILABLE:
            print("⚠️ OpenSearch not available")
            return
        
        try:
            if use_aws_auth and AWS_AUTH_AVAILABLE:
                # AWS Auth - store session for token refresh
                self.aws_session = session.Session()
                
                # Extract hostname from endpoint
                self.aws_host = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')[0]
                
                # Determine port
                self.port = 443
                if ':' in self.opensearch_endpoint:
                    port_part = self.opensearch_endpoint.split(':')[-1].split('/')[0]
                    try:
                        self.port = int(port_part)
                    except ValueError:
                        self.port = 443
                
                self.hostname = self.aws_host
                
                # Initialize with fresh credentials
                self._refresh_aws_auth()
                
                print(f"✅ Connected to AWS OpenSearch: {self.opensearch_endpoint}")
            else:
                # Basic authentication
                host_parts = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')
                self.hostname = host_parts[0]
                self.port = int(host_parts[1]) if len(host_parts) > 1 else 9200
                
                self.client = OpenSearch(
                    hosts=[{'host': self.hostname, 'port': self.port}],
                    use_ssl=use_ssl,
                    verify_certs=verify_certs,
                    connection_class=RequestsHttpConnection
                )
                print(f"✅ Connected to OpenSearch: {self.opensearch_endpoint}")
        except Exception as e:
            print(f"⚠️ Failed to connect to OpenSearch: {e}")
            import traceback
            print(traceback.format_exc())
        
        # Initialize embedding service (Azure)
        if use_azure_embeddings and AZURE_EMBEDDINGS_AVAILABLE:
            try:
                self.azure_embedding_service = EmbeddingService(
                    user_sid=user_sid,
                    cert_path=azure_cert_path,
                    config_path=azure_config_path
                )
                print("✅ Azure OpenAI Embeddings service initialized")
            except Exception as e:
                print(f"⚠️ Failed to initialize Azure Embeddings service: {e}")
    
    def _refresh_aws_auth(self):
        """Refresh AWS authentication credentials and update OpenSearch client."""
        if not self.use_aws_auth or not AWS_AUTH_AVAILABLE or not self.aws_session:
            return False
        
        try:
            credentials = self.aws_session.get_credentials()
            
            if not credentials:
                print("⚠️ Failed to get AWS credentials for refresh")
                return False
            
            awsauth = AWSRequestsAuth(
                aws_access_key=credentials.access_key,
                aws_secret_access_key=credentials.secret_key,
                aws_token=credentials.token,
                aws_host=self.aws_host,
                aws_region=self.region,
                aws_service='es'
            )
            
            self.client = OpenSearch(
                hosts=[{'host': self.hostname, 'port': self.port}],
                http_auth=awsauth,
                use_ssl=self.use_ssl,
                verify_certs=self.verify_certs,
                connection_class=RequestsHttpConnection
            )
            
            return True
        except Exception as e:
            print(f"⚠️ Failed to refresh AWS authentication: {e}")
            return False
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        use_semantic: bool = False,
        application_name: Optional[str] = None,
        seal_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search OpenSearch index."""
        if not self.client:
            return []
        
        try:
            query_body = {"size": top_k}
            
            if use_semantic and self.azure_embedding_service:
                # Generate embedding for semantic search
                try:
                    query_embedding = self.azure_embedding_service.embed_text(query)
                    
                    if query_embedding:
                        # Build kNN query
                        knn_query = {
                            "field": "embedding",
                            "query_vector": query_embedding,
                            "k": top_k,
                            "num_candidates": top_k * 2
                        }
                        
                        filter_clauses = []
                        if application_name:
                            filter_clauses.append({"term": {"application_name": application_name}})
                        if seal_id:
                            filter_clauses.append({"term": {"seal_id": seal_id}})
                        
                        if filter_clauses:
                            query_body["post_filter"] = {
                                "bool": {"must": filter_clauses}
                            }
                        
                        query_body["knn"] = knn_query
                        query_body["query"] = {"match_all": {}}
                except Exception as e:
                    print(f"⚠️ Failed to generate embedding: {e}")
                    use_semantic = False
            
            if not use_semantic:
                # Text-based search
                must_clauses = [{
                    "multi_match": {
                        "query": query,
                        "fields": ["code", "summary", "fqn"]
                    }
                }]
                
                if application_name:
                    must_clauses.append({"term": {"application_name": application_name}})
                if seal_id:
                    must_clauses.append({"term": {"seal_id": seal_id}})
                
                query_body["query"] = {
                    "bool": {"must": must_clauses}
                }
            
            # Execute search with retry logic
            max_retries = 2
            retry_count = 0
            
            while retry_count <= max_retries:
                try:
                    response = self.client.search(
                        body=query_body,
                        index=self.index_name
                    )
                    break
                except Exception as e:
                    error_str = str(e)
                    is_token_error = (
                        '403' in error_str or 
                        'expired' in error_str.lower() or 
                        'AuthorizationException' in type(e).__name__
                    )
                    
                    if is_token_error and retry_count < max_retries and self.use_aws_auth:
                        print(f"⚠️ Token expired, refreshing AWS credentials (attempt {retry_count + 1}/{max_retries})...")
                        if self._refresh_aws_auth():
                            retry_count += 1
                            continue
                        else:
                            raise Exception(f"Failed to refresh AWS credentials: {error_str}")
                    else:
                        raise
            
            results = []
            for hit in response['hits']['hits']:
                source = hit['_source']
                results.append({
                    'id': hit['_id'],
                    'chunk_id': source.get('chunk_id', hit['_id']),
                    'score': hit['_score'],
                    'fqn': source.get('fqn', ''),
                    'type': source.get('type', ''),
                    'file_path': source.get('file_path', ''),
                    'filetype': source.get('filetype', ''),
                    'module': source.get('module'),
                    'code': source.get('code', ''),
                    'summary': source.get('summary', ''),
                    'application_name': source.get('application_name', ''),
                    'seal_id': source.get('seal_id', ''),
                })
            
            return results
        except Exception as e:
            print(f"⚠️ Search error: {e}")
            import traceback
            print(traceback.format_exc())
            return []


class GraphLoader:
    """Load and query NetworkX graph."""
    
    def __init__(self, graph_file: str):
        """Initialize graph loader."""
        self.graph = None
        if NETWORKX_AVAILABLE and Path(graph_file).exists():
            try:
                with open(graph_file, 'rb') as f:
                    self.graph = pickle.load(f)
                print(f"✅ Loaded graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
            except Exception as e:
                print(f"⚠️ Failed to load graph: {e}")
        else:
            print(f"⚠️ Graph file not found or NetworkX not available: {graph_file}")
    
    def get_context_for_chunks(self, chunk_ids: List[str], max_nodes: int = 10) -> str:
        """
        Get graph context for given chunk IDs.
        
        Args:
            chunk_ids: List of chunk IDs to find in graph
            max_nodes: Maximum number of related nodes to include
        
        Returns:
            Graph context as string
        """
        if not self.graph:
            return ""
        
        context_parts = []
        found_nodes = []
        
        # Find nodes matching chunk IDs
        for chunk_id in chunk_ids[:5]:  # Limit to first 5 chunks
            # Try to find node by chunk_id
            for node_id in self.graph.nodes():
                node_data = self.graph.nodes[node_id]
                if node_data.get('chunk_id') == chunk_id or str(node_id) == chunk_id:
                    found_nodes.append(node_id)
                    break
        
        if not found_nodes:
            return ""
        
        # Get neighbors of found nodes
        related_nodes = set(found_nodes)
        for node_id in found_nodes[:max_nodes]:
            neighbors = list(self.graph.neighbors(node_id))[:5]
            related_nodes.update(neighbors)
        
        # Build context
        for node_id in list(related_nodes)[:max_nodes]:
            node_data = self.graph.nodes[node_id]
            node_type = node_data.get('type', 'unknown')
            node_fqn = node_data.get('fqn', str(node_id))
            
            # Get edges
            edges = []
            for neighbor in self.graph.neighbors(node_id):
                edge_data = self.graph.get_edge_data(node_id, neighbor, {})
                edge_type = edge_data.get('type', 'related')
                neighbor_data = self.graph.nodes[neighbor]
                neighbor_fqn = neighbor_data.get('fqn', str(neighbor))
                edges.append(f"{edge_type} -> {neighbor_fqn}")
            
            context_parts.append(f"Node: {node_fqn} (type: {node_type})")
            if edges:
                context_parts.append(f"  Relationships: {', '.join(edges[:3])}")
        
        return "\n".join(context_parts) if context_parts else ""


def main():
    parser = argparse.ArgumentParser(description="Query OpenSearch and generate streaming LLM response")
    
    # Query arguments
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--top-k", type=int, default=10, help="Number of top results (default: 10)")
    
    # OpenSearch arguments
    parser.add_argument("--opensearch-host", help="OpenSearch host/endpoint")
    parser.add_argument("--opensearch-index", default="code_chunks", help="OpenSearch index name")
    parser.add_argument("--opensearch-config", help="Path to config.ini file for OpenSearch configuration")
    parser.add_argument("--opensearch-use-aws-auth", action="store_true", default=True, help="Use AWS authentication (default: True)")
    parser.add_argument("--opensearch-no-aws-auth", action="store_false", dest="opensearch_use_aws_auth", help="Disable AWS authentication")
    parser.add_argument("--opensearch-region", default="us-east-1", help="AWS region for OpenSearch")
    parser.add_argument("--opensearch-use-ssl", action="store_true", default=True, help="Use SSL for OpenSearch")
    parser.add_argument("--opensearch-verify-certs", action="store_true", default=True, help="Verify SSL certificates")
    
    # Filter arguments
    parser.add_argument("--application-name", help="Filter results by application name")
    parser.add_argument("--seal-id", help="Filter results by seal ID")
    
    # Embedding arguments
    parser.add_argument("--use-azure-embeddings", action="store_true", help="Use Azure OpenAI Embeddings for semantic search")
    parser.add_argument("--use-semantic", action="store_true", help="Use semantic/vector search")
    parser.add_argument("--user-sid", default="default_user", help="User session ID for Azure")
    parser.add_argument("--azure-cert-path", help="Path to Azure certificate file (.pem)")
    parser.add_argument("--azure-config-path", help="Path to config.ini file for Azure")
    
    # Graph arguments
    parser.add_argument("--graph-file", help="Path to NetworkX graph file (.pkl)")
    parser.add_argument("--use-graph", action="store_true", help="Include graph context in LLM response")
    
    # LLM arguments
    parser.add_argument("--use-llm", action="store_true", help="Generate LLM response")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming (not recommended)")
    
    args = parser.parse_args()
    
    # Determine config paths
    config_path = args.opensearch_config
    azure_config_path = args.azure_config_path
    if azure_config_path is None and config_path:
        azure_config_path = config_path
    
    # Validate arguments
    if not args.opensearch_host and not config_path:
        parser.error("Either --opensearch-host or --opensearch-config is required")
    
    if args.use_semantic and not args.use_azure_embeddings:
        parser.error("--use-semantic requires --use-azure-embeddings")
    
    # Initialize searcher
    print("\n🔍 Initializing OpenSearch searcher...")
    searcher = StandaloneSearcher(
        host=args.opensearch_host,
        index=args.opensearch_index,
        config_path=config_path,
        use_aws_auth=args.opensearch_use_aws_auth,
        region=args.opensearch_region,
        use_ssl=args.opensearch_use_ssl,
        verify_certs=args.opensearch_verify_certs,
        use_azure_embeddings=args.use_azure_embeddings,
        user_sid=args.user_sid,
        azure_cert_path=args.azure_cert_path,
        azure_config_path=azure_config_path
    )
    
    # Search
    print(f"\n🔎 Searching for: '{args.query}'")
    results = searcher.search(
        query=args.query,
        top_k=args.top_k,
        use_semantic=args.use_semantic,
        application_name=args.application_name,
        seal_id=args.seal_id
    )
    
    print(f"✅ Found {len(results)} results\n")
    
    # Display results
    if results:
        print("=" * 80)
        print("SEARCH RESULTS")
        print("=" * 80)
        for i, result in enumerate(results, 1):
            print(f"\n[{i}] {result.get('fqn', 'unknown')}")
            print(f"    File: {result.get('file_path', 'unknown')}")
            if result.get('module'):
                print(f"    Module: {result.get('module')}")
            print(f"    Type: {result.get('type', 'unknown')}")
            print(f"    Score: {result.get('score', 0):.4f}")
            print(f"    Code preview: {result.get('code', '')[:100]}...")
        print("\n" + "=" * 80)
    
    # Load graph if requested
    graph_loader = None
    graph_context = None
    if args.graph_file and args.use_graph:
        print("\n📊 Loading graph...")
        graph_loader = GraphLoader(args.graph_file)
        if graph_loader.graph and results:
            chunk_ids = [r.get('chunk_id') for r in results if r.get('chunk_id')]
            graph_context = graph_loader.get_context_for_chunks(chunk_ids)
            if graph_context:
                print("✅ Graph context extracted")
    
    # Generate LLM response if requested
    if args.use_llm:
        print("\n🤖 Generating LLM response...\n")
        print("=" * 80)
        print("LLM RESPONSE")
        print("=" * 80)
        print()
        
        llm_client = LLMClient(
            user_sid=args.user_sid,
            cert_path=args.azure_cert_path,
            config_path=azure_config_path
        )
        
        if not args.no_stream:
            # Streaming response
            for chunk in llm_client.generate_response_stream(
                query=args.query,
                context=results,
                graph_context=graph_context
            ):
                print(chunk, end='', flush=True)
            print()  # New line after streaming
        else:
            # Non-streaming (collect all chunks first)
            response_parts = []
            for chunk in llm_client.generate_response_stream(
                query=args.query,
                context=results,
                graph_context=graph_context
            ):
                response_parts.append(chunk)
            print(''.join(response_parts))
        
        print("\n" + "=" * 80)
    else:
        print("\n💡 Tip: Use --use-llm to generate an LLM response based on search results")


if __name__ == "__main__":
    main()

