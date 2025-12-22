"""
Completely standalone script to query OpenSearch chunks and generate HTML report with Mermaid graph.
No dependencies on project structure.

Usage:
  python standalone_query_to_html_independent.py \
    --query "who calls startDemo" \
    --opensearch-host localhost:9200 \
    --opensearch-index code_chunks \
    --graph-file ./output/graph.pkl \
    --output report.html

Requirements:
  pip install opensearch-py networkx aws-requests-auth boto3
"""

import argparse
import html
import pickle
import os
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

# OpenAI for embeddings (for semantic search)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not available. Install: pip install openai (optional, for semantic search)")

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
    print("⚠️ Azure LLM not available. Install: pip install langchain-openai azure-identity (optional, for LLM responses)")


class EmbeddingService:
    """Azure OpenAI Embedding Service with certificate-based authentication."""
    
    def __init__(self, user_sid: str = "default_user", cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """
        Initialize the embedding service.
        
        Args:
            user_sid: User session ID for multi-tenancy
            cert_path: Path to certificate file (optional, will try default locations)
            config_path: Path to config.ini file (optional, defaults to script directory)
        """
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
        
        print(f"Loading config from {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        llm_config = configparser.ConfigParser()
        llm_config.read(file_path)
        return llm_config
    
    @staticmethod
    def get_access_token(cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """Obtain access token using certificate-based authentication."""
        print("Obtaining access token.")
        config = EmbeddingService.load_config(config_path)
        current_dir = os.path.dirname(__file__)
        
        try:
            # Certificate path - use provided path or default location
            if cert_path is None:
                cert_path = os.path.join(current_dir, "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem")
            
            # Try to find certificate if default path doesn't exist
            if not os.path.exists(cert_path):
                # Try alternative locations
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
            
            print(f"Certificate path: {cert_path}")
            
            credential = CertificateCredential(
                tenant_id=config['azure_openai']['azure_tenant_id'],
                client_id=config['azure_openai']['azure_client_id'],
                certificate_path=cert_path
            )
            
            access_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
            return access_token
        except ClientAuthenticationError as e:
            error_msg = str(e) if hasattr(e, '__str__') else getattr(e, 'message', 'Unknown error')
            print(f"Authentication failed: {error_msg}")
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
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        use_azure_embeddings: bool = False,
        user_sid: str = "default_user",
        azure_cert_path: Optional[str] = None,
        azure_config_path: Optional[str] = None
    ):
        """
        Initialize OpenSearch searcher.
        
        Args:
            host: OpenSearch endpoint (optional if using config file)
            index: OpenSearch index name (optional if using config file)
            config_path: Path to config.ini file (optional)
            use_aws_auth: Use AWS authentication (default: True)
            region: AWS region (optional, will use config or default)
            use_ssl: Use SSL for connection (default: True)
            verify_certs: Verify SSL certificates (default: True)
            openai_api_key: OpenAI API key for semantic search (optional)
            embedding_model: Embedding model name (default: text-embedding-3-small)
            use_azure_embeddings: Use Azure OpenAI Embeddings service (default: False)
            user_sid: User session ID for Azure embeddings (default: default_user)
            azure_cert_path: Path to Azure certificate file (.pem)
            azure_config_path: Path to config.ini file for Azure (default: script directory)
        """
        self.host = host
        self.index = index
        self.client = None
        self.openai_client = None
        self.azure_embedding_service = None
        self.embedding_model = embedding_model
        self.use_azure_embeddings = use_azure_embeddings
        
        # Store AWS auth configuration for token refresh (same as build script)
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
            print(f"✅ Loaded config from {config_path}")
            print(f"   Sections found: {self.config.sections()}")
            
            # Extract OpenSearch config from config file
            if 'aws_info' in self.config:
                self.opensearch_endpoint = self.config['aws_info'].get('opensearch_endpoint', host or '')
                self.index_name = self.config['aws_info'].get('index_name', index or 'code_chunks')
                self.region = self.config['aws_info'].get('region', region or 'us-east-1')
            else:
                # Fallback to provided parameters
                self.opensearch_endpoint = host or ''
                self.index_name = index or 'code_chunks'
                self.region = region or 'us-east-1'
        else:
            # Use provided parameters
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
                # AWS Auth - store session for token refresh (same as build script)
                self.aws_session = session.Session()
                
                # Extract hostname from endpoint (remove protocol and port)
                self.aws_host = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')[0]
                
                # Determine port (default 443 for HTTPS)
                self.port = 443
                if ':' in self.opensearch_endpoint:
                    port_part = self.opensearch_endpoint.split(':')[-1].split('/')[0]
                    try:
                        self.port = int(port_part)
                    except ValueError:
                        self.port = 443
                
                self.hostname = self.aws_host
                
                # Initialize with fresh credentials (same as build script)
                self._refresh_aws_auth()
                
                print(f"✅ Connected to AWS OpenSearch: {self.opensearch_endpoint}")
            else:
                # Basic authentication (for local development)
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
        
        # Initialize embedding service (Azure or OpenAI)
        if use_azure_embeddings and AZURE_EMBEDDINGS_AVAILABLE:
            try:
                self.azure_embedding_service = EmbeddingService(
                    user_sid=user_sid,
                    cert_path=azure_cert_path,
                    config_path=azure_config_path
                )
                print("✅ Azure OpenAI Embeddings service initialized for semantic search")
            except Exception as e:
                print(f"⚠️ Failed to initialize Azure Embeddings service: {e}")
                print("   Falling back to OpenAI if API key provided")
                use_azure_embeddings = False
        
        if not use_azure_embeddings and openai_api_key and OPENAI_AVAILABLE:
            self.openai_client = OpenAI(api_key=openai_api_key)
            print("✅ OpenAI client initialized for semantic search")
    
    def _refresh_aws_auth(self):
        """Refresh AWS authentication credentials and update OpenSearch client (same as build script)."""
        if not self.use_aws_auth or not AWS_AUTH_AVAILABLE or not self.aws_session:
            return False
        
        try:
            # Get fresh credentials from session
            credentials = self.aws_session.get_credentials()
            
            if not credentials:
                print("⚠️ Failed to get AWS credentials for refresh")
                return False
            
            # Create new AWS auth with fresh credentials
            # AWSRequestsAuth expects individual credential components
            awsauth = AWSRequestsAuth(
                aws_access_key=credentials.access_key,
                aws_secret_access_key=credentials.secret_key,
                aws_token=credentials.token,
                aws_host=self.aws_host,
                aws_region=self.region,
                aws_service='es'
            )
            
            # Recreate OpenSearch client with fresh auth
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
    
    def verify_index_structure(self) -> bool:
        """
        Verify that the index exists and has the expected mapping structure.
        Expected mapping matches build script:
        - chunk_id (keyword)
        - type (keyword)
        - fqn (keyword)
        - file_path (keyword)
        - code (text)
        - summary (text)
        - application_name (keyword)
        - seal_id (keyword)
        - embedding (knn_vector)
        
        Returns:
            True if index exists and structure is valid, False otherwise
        """
        if not self.client:
            return False
        
        try:
            # Check if index exists
            if not self.client.indices.exists(index=self.index_name):
                print(f"⚠️ Index '{self.index_name}' does not exist")
                return False
            
            # Get index mapping
            mapping = self.client.indices.get_mapping(index=self.index_name)
            index_mapping = mapping.get(self.index_name, {}).get('mappings', {}).get('properties', {})
            
            # Expected fields from build script mapping
            expected_fields = {
                'chunk_id': 'keyword',
                'type': 'keyword',
                'fqn': 'keyword',
                'file_path': 'keyword',
                'code': 'text',
                'summary': 'text',
                'application_name': 'keyword',
                'seal_id': 'keyword',
                'embedding': 'knn_vector'
            }
            
            # Verify required fields exist
            missing_fields = []
            for field, expected_type in expected_fields.items():
                if field not in index_mapping:
                    missing_fields.append(field)
                else:
                    actual_type = index_mapping[field].get('type', '')
                    if expected_type == 'knn_vector':
                        if actual_type != 'knn_vector':
                            print(f"⚠️ Field '{field}' has type '{actual_type}', expected 'knn_vector'")
                    elif actual_type != expected_type:
                        print(f"⚠️ Field '{field}' has type '{actual_type}', expected '{expected_type}'")
            
            if missing_fields:
                print(f"⚠️ Missing required fields in index mapping: {', '.join(missing_fields)}")
                return False
            
            print(f"✅ Index '{self.index_name}' structure verified")
            return True
        except Exception as e:
            print(f"⚠️ Error verifying index structure: {e}")
            return False
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        use_semantic: bool = False,
        application_name: Optional[str] = None,
        seal_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search OpenSearch index.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            use_semantic: Use semantic/vector search (requires embeddings)
            application_name: Filter by application name (optional)
            seal_id: Filter by seal ID (optional)
        """
        if not self.client:
            return []
        
        try:
            # Build query
            query_body = {
                    "size": top_k,
            }
            
            if use_semantic:
                # Generate embedding for semantic search (Azure or OpenAI)
                query_embedding = None
                try:
                    if self.use_azure_embeddings and self.azure_embedding_service:
                        # Use Azure embeddings
                        query_embedding = self.azure_embedding_service.embed_text(query)
                    elif self.openai_client:
                        # Use OpenAI embeddings
                        response = self.openai_client.embeddings.create(
                            model=self.embedding_model,
                            input=query
                        )
                        query_embedding = response.data[0].embedding
                    else:
                        print("⚠️ No embedding service available for semantic search")
                        use_semantic = False
                except Exception as e:
                    print(f"⚠️ Failed to generate embedding: {e}")
                    use_semantic = False
                
                if query_embedding:
                    # Build kNN query - OpenSearch format
                    # Use hybrid approach: combine kNN with query filters
                    knn_query = {
                        "field": "embedding",
                        "query_vector": query_embedding,
                        "k": top_k,
                        "num_candidates": top_k * 2
                    }
                    
                    # Build filter clauses for post_filter or query
                    filter_clauses = []
                    if application_name:
                        filter_clauses.append({"term": {"application_name": application_name}})
                    if seal_id:
                        filter_clauses.append({"term": {"seal_id": seal_id}})
                    
                    # Use post_filter for filters (more compatible across OpenSearch versions)
                    if filter_clauses:
                        query_body["post_filter"] = {
                            "bool": {
                                "must": filter_clauses
                            }
                        }
                    
                    # OpenSearch kNN query - kNN at top level
                    query_body["knn"] = knn_query
                    # Add match_all query for hybrid search (optional but can help)
                    query_body["query"] = {"match_all": {}}
                else:
                    use_semantic = False
            
            if not use_semantic:
                # Text-based search
                must_clauses = [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["code", "summary", "fqn"]
                        }
                    }
                ]
                
                # Add filters
                if application_name:
                    must_clauses.append({"term": {"application_name": application_name}})
                if seal_id:
                    must_clauses.append({"term": {"seal_id": seal_id}})
                
                query_body["query"] = {
                    "bool": {
                        "must": must_clauses
                    }
                }
            
            # Use same pattern as build script - OpenSearch client API
            # Add retry logic for token expiration (same as build script)
            max_retries = 2
            retry_count = 0
            
            while retry_count <= max_retries:
                try:
                    response = self.client.search(
                        body=query_body,
                        index=self.index_name
                    )
                    break  # Success, exit retry loop
                except Exception as e:
                    error_str = str(e)
                    error_type = type(e).__name__
                    
                    # Check if it's a token expiration error
                    is_token_error = (
                        '403' in error_str or 
                        'expired' in error_str.lower() or 
                        'AuthorizationException' in error_type or
                        'token' in error_str.lower() and 'expired' in error_str.lower()
                    )
                    
                    if is_token_error and retry_count < max_retries and self.use_aws_auth:
                        # Token expired, refresh and retry
                        print(f"⚠️ Token expired, refreshing AWS credentials (attempt {retry_count + 1}/{max_retries})...")
                        if self._refresh_aws_auth():
                            retry_count += 1
                            continue
                        else:
                            # Failed to refresh
                            raise Exception(f"Failed to refresh AWS credentials: {error_str}")
                    else:
                        # Not a token error or max retries reached
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


class StandaloneGraphLoader:
    """Self-contained graph loader supporting both simple and rich schemas."""
    
    def __init__(self, graph_file: str):
        self.graph = None
        if NETWORKX_AVAILABLE and Path(graph_file).exists():
            try:
                with open(graph_file, 'rb') as f:
                    self.graph = pickle.load(f)
                print(f"✅ Loaded graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
            except Exception as e:
                print(f"⚠️ Failed to load graph: {e}")
    
    def find_related(self, chunk_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """Find related chunks in graph (supports both simple and rich schemas)."""
        if not self.graph:
            return []
        
        # Try to find node by chunk_id (for simple schema) or by entity_type (for rich schema)
        node_id = None
        
        # First, try direct chunk_id match
        if chunk_id in self.graph.nodes():
            node_id = chunk_id
        else:
            # Try with chunk_ prefix
            prefixed_id = f"chunk_{chunk_id}" if not chunk_id.startswith('chunk_') else chunk_id
            if prefixed_id in self.graph.nodes():
                node_id = prefixed_id
            else:
                # Search for node with matching chunk_id attribute (for rich schema)
                for nid, data in self.graph.nodes(data=True):
                    if data.get('chunk_id') == chunk_id or data.get('chunk_id') == prefixed_id:
                        node_id = nid
                        break
        
        if not node_id:
            return []
        
        related = []
        visited = set()
        queue = [(node_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth or current in visited:
                continue
            
            visited.add(current)
            
            # Get neighbors (both successors and predecessors)
            for neighbor in list(self.graph.successors(current)) + list(self.graph.predecessors(current)):
                if neighbor not in visited:
                    edge_data = self.graph.get_edge_data(current, neighbor)
                    if edge_data:
                        # Handle MultiDiGraph edge data (can have multiple edges)
                        edge_info = list(edge_data.values())[0] if edge_data else {}
                        rel_type = edge_info.get('relationship', 'related')
                        
                        # Get node data
                        node_data = self.graph.nodes[neighbor]
                        entity_type = node_data.get('entity_type', 'CodeChunk')
                        
                        related.append({
                            'chunk_id': neighbor,
                            'relationship': rel_type,
                            'fqn': node_data.get('fqn', ''),
                            'entity_type': entity_type,
                            'name': node_data.get('name', ''),
                        })
                        queue.append((neighbor, depth + 1))
        
        return related


class TokenManager:
    """Manages Azure OpenAI access tokens with certificate-based authentication."""
    
    def __init__(self, cert_path: Optional[str] = None, config_path: Optional[str] = None):
        """
        Initialize token manager.
        
        Args:
            cert_path: Path to certificate file (.pem)
            config_path: Path to config.ini file
        """
        self.cert_path = cert_path
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.access_token = None
        self._refresh_token()
    
    @staticmethod
    def _load_config(config_path: Optional[str] = None):
        """Load configuration from config.ini file."""
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            config_path = os.path.join(current_dir, "config.ini")
        
        if not os.path.exists(config_path):
            print(f"⚠️ Config file not found: {config_path}")
            return None
        
        print(f"Loading config from {config_path}")
        config = configparser.ConfigParser()
        config.read(config_path)
        return config
    
    def _refresh_token(self):
        """Obtain or refresh access token."""
        if not self.config or 'azure_openai' not in self.config:
            print("⚠️ Azure OpenAI config not found in config file")
            return None
        
        try:
            # Find certificate file - use same pattern as EmbeddingService
            if self.cert_path is None:
                current_dir = os.path.dirname(__file__)
                cert_path = os.path.join(current_dir, "..", "..", "discoveryeng.dev.azure.jpmchase.net.pem")
                
                # Try to find certificate if default path doesn't exist
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
                        print(f"⚠️ Certificate file not found. Tried: {cert_path}")
                        return None
            else:
                cert_path = self.cert_path
            
            if not os.path.exists(cert_path):
                print(f"⚠️ Certificate file not found: {cert_path}")
                return None
            
            print(f"Certificate path: {cert_path}")
            print("Obtaining access token...")
            
            credential = CertificateCredential(
                tenant_id=self.config['azure_openai']['azure_tenant_id'],
                client_id=self.config['azure_openai']['azure_client_id'],
                certificate_path=cert_path
            )
            
            self.access_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
            if self.access_token:
                print("✅ Access token obtained")
            return self.access_token
        except ClientAuthenticationError as e:
            error_msg = str(e) if hasattr(e, '__str__') else getattr(e, 'message', 'Unknown error')
            print(f"⚠️ Authentication failed: {error_msg}")
            return None
        except Exception as e:
            print(f"⚠️ Failed to obtain access token: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
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
        """
        Initialize LLM client.
        
        Args:
            token_manager: TokenManager instance (optional, will create if not provided)
            user_sid: User session ID for multi-tenancy
            cert_path: Path to certificate file (optional)
            config_path: Path to config.ini file (optional)
        """
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
            # Use same endpoint and API key pattern as EmbeddingService in build script
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
            import traceback
            print(traceback.format_exc())
            self.chat_client = None
    
    def get_chat_client(self):
        """Get chat client with latest token."""
        if self.chat_client and self.token_manager:
            # Ensure the client uses the latest token
            access_token = self.token_manager.get_token()
            if access_token:
                self.chat_client.default_headers["Authorization"] = f"Bearer {access_token}"
        return self.chat_client
    
    def generate_response(
        self,
        query: str,
        context: List[Dict[str, Any]],
        stream: bool = True
    ) -> str:
        """
        Generate LLM response with context from search results.
        
        Args:
            query: User query
            context: List of search results to use as context
            stream: Whether to stream the response (default: True)
        
        Returns:
            Generated response text
        """
        if not self.chat_client:
            return "LLM client not available. Please check configuration."
        
        # Build context from search results
        context_text = "Relevant code snippets from the codebase:\n\n"
        for i, result in enumerate(context[:5], 1):  # Use top 5 results
            context_text += f"--- Result {i} ---\n"
            context_text += f"File: {result.get('file_path', 'unknown')}\n"
            context_text += f"Type: {result.get('type', 'unknown')}\n"
            context_text += f"FQN: {result.get('fqn', 'unknown')}\n"
            context_text += f"Code:\n{result.get('code', '')[:500]}\n\n"  # Limit code length
        
        # Build prompt
        prompt = f"""You are a helpful code assistant. Answer the user's question based on the provided code context.

Context:
{context_text}

User Question: {query}

Please provide a clear and concise answer based on the code context provided. If the context doesn't contain enough information, say so."""
        
        try:
            # Get client with latest token
            client = self.get_chat_client()
            if not client:
                return "Failed to get LLM client"
            
            if stream:
                # Streaming response
                response_parts = []
                for chunk in client.stream(prompt):
                    if hasattr(chunk, 'content') and chunk.content:
                        response_parts.append(chunk.content)
                        print(chunk.content, end='', flush=True)
                print()  # New line after streaming
                return ''.join(response_parts)
            else:
                # Non-streaming response
                response = client.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"Error generating response: {str(e)}"


def mermaid_from_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    """Generate Mermaid diagram from nodes and edges."""
    if not nodes:
        return "graph LR\n    A[No nodes]"
    
    node_lines = []
    for n in nodes:
        label = n.get('label', n.get('fqn', n.get('name', n.get('id', ''))))
        short = html.escape(str(label).split('.')[-1][:30])
        node_id = n.get('id', '').replace('-', '_').replace('.', '_')
        node_lines.append(f'    {node_id}["{short}"]')
    
    edge_lines = []
    for e in edges:
        from_id = e.get('from', '').replace('-', '_').replace('.', '_')
        to_id = e.get('to', '').replace('-', '_').replace('.', '_')
        rel = html.escape(e.get('relationship', 'rel')[:20])
        edge_lines.append(f'    {from_id} -->|"{rel}"| {to_id}')
    
    body = "\n".join(node_lines + edge_lines)
    return f"flowchart LR\n{body}"


def build_html(query: str, results: List[Dict[str, Any]], mermaid_snippet: str, llm_response: Optional[str] = None) -> str:
    """Build HTML report."""
    rows = []
    for r in results:
        rows.append(f"""
        <tr>
          <td>{html.escape(str(r.get('score', '')))}</td>
          <td>{html.escape(r.get('fqn', ''))}</td>
          <td>{html.escape(r.get('type', ''))}</td>
          <td>{html.escape(r.get('file_path', ''))}</td>
          <td>{html.escape(r.get('application_name', ''))}</td>
          <td>{html.escape(r.get('seal_id', ''))}</td>
        </tr>
        """)
    
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Query Report</title>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: true }});
  </script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 13px; }}
    th {{ background: #f4f4f4; text-align: left; }}
    .mermaid {{ border: 1px solid #ddd; padding: 12px; border-radius: 6px; margin-top: 16px; }}
    pre {{ background: #f5f5f5; padding: 12px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h2>Query</h2>
  <pre>{html.escape(query)}</pre>

  <h2>Top Results ({len(results)})</h2>
  <table>
    <thead><tr><th>Score</th><th>FQN</th><th>Type</th><th>File Path</th><th>Application</th><th>Seal ID</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <h2>Graph Visualization</h2>
  <div class="mermaid">
{mermaid_snippet}
  </div>
  
  {f'''
  <h2>LLM Response</h2>
  <div style="background: #f9f9f9; padding: 16px; border-radius: 6px; margin-top: 16px; white-space: pre-wrap;">
{html.escape(llm_response or "No LLM response generated")}
  </div>
  ''' if llm_response else ''}
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Query OpenSearch and generate HTML report")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--opensearch-host", help="OpenSearch host/endpoint (e.g., localhost:9200 or search-domain.us-east-1.es.amazonaws.com)")
    parser.add_argument("--opensearch-index", default="code_chunks", help="OpenSearch index name")
    parser.add_argument("--opensearch-config", help="Path to config.ini file for OpenSearch configuration")
    parser.add_argument("--opensearch-use-aws-auth", action="store_true", default=True, help="Use AWS authentication for OpenSearch (default: True)")
    parser.add_argument("--opensearch-no-aws-auth", action="store_false", dest="opensearch_use_aws_auth", help="Disable AWS authentication (use basic auth)")
    parser.add_argument("--opensearch-region", default="us-east-1", help="AWS region for OpenSearch (default: us-east-1)")
    parser.add_argument("--opensearch-use-ssl", action="store_true", default=True, help="Use SSL for OpenSearch connection (default: True)")
    parser.add_argument("--opensearch-verify-certs", action="store_true", default=True, help="Verify SSL certificates (default: True)")
    parser.add_argument("--application-name", help="Filter results by application name")
    parser.add_argument("--seal-id", help="Filter results by seal ID")
    parser.add_argument("--openai-api-key", help="OpenAI API key for embeddings")
    parser.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model")
    parser.add_argument("--use-azure-embeddings", action="store_true", help="Use Azure OpenAI Embeddings service (requires config.ini)")
    parser.add_argument("--use-semantic", action="store_true", help="Use semantic/vector search (requires --openai-api-key or --use-azure-embeddings)")
    parser.add_argument("--user-sid", default="default_user", help="User session ID for Azure embeddings (default: default_user)")
    parser.add_argument("--azure-cert-path", help="Path to Azure certificate file (.pem)")
    parser.add_argument("--azure-config-path", help="Path to config.ini file (default: script directory)")
    parser.add_argument("--graph-file", help="Graph pickle file (optional)")
    parser.add_argument("--output", required=True, help="Output HTML file")
    parser.add_argument("--max-results", type=int, default=10, help="Max search results")
    parser.add_argument("--graph-depth", type=int, default=2, help="Graph traversal depth")
    
    # LLM arguments (query-specific)
    parser.add_argument("--use-llm", action="store_true", help="Generate LLM response with context from search results")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming for LLM response")
    args = parser.parse_args()
    
    # Determine config path (use opensearch-config if provided, otherwise try default location)
    config_path = args.opensearch_config
    if config_path is None:
        current_dir = os.path.dirname(__file__)
        default_config = os.path.join(current_dir, "config.ini")
        if os.path.exists(default_config):
            config_path = default_config
    
    # Check if config file exists and has OpenSearch settings
    opensearch_from_config = False
    if config_path and os.path.exists(config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        if 'aws_info' in config:
            opensearch_from_config = bool(config['aws_info'].get('opensearch_endpoint'))
    
    # Determine Azure config path (use azure-config-path if provided, otherwise try default location or opensearch-config)
    azure_config_path = args.azure_config_path
    if azure_config_path is None:
        if config_path:
            azure_config_path = config_path  # Use same config file
        else:
            current_dir = os.path.dirname(__file__)
            default_config = os.path.join(current_dir, "config.ini")
            if os.path.exists(default_config):
                azure_config_path = default_config
    
    # Validate arguments - allow config file to provide OpenSearch settings
    if not args.opensearch_host and not opensearch_from_config:
        parser.error("Either --opensearch-host or --opensearch-config (with opensearch_endpoint in [aws_info] section) is required")
    
    if args.use_semantic and not args.openai_api_key and not args.use_azure_embeddings:
        parser.error("Either --openai-api-key or --use-azure-embeddings is required when using --use-semantic")
    
    # Search
    searcher = StandaloneSearcher(
        host=args.opensearch_host,
        index=args.opensearch_index,
        config_path=config_path,  # Use determined config path
        use_aws_auth=args.opensearch_use_aws_auth,
        region=args.opensearch_region,
        use_ssl=args.opensearch_use_ssl,
        verify_certs=args.opensearch_verify_certs,
        openai_api_key=args.openai_api_key,
        embedding_model=args.embedding_model,
        use_azure_embeddings=args.use_azure_embeddings,
        user_sid=args.user_sid,
        azure_cert_path=args.azure_cert_path,
        azure_config_path=azure_config_path
    )
    
    # Verify index structure matches build script mapping
    if searcher.client:
        print("\n🔍 Verifying index structure...")
        searcher.verify_index_structure()
        print()  # Empty line for readability
    
    results = searcher.search(
        query=args.query,
        top_k=args.max_results,
        use_semantic=args.use_semantic,
        application_name=args.application_name,
        seal_id=args.seal_id
    )
    print(f"✅ Found {len(results)} results")
    
    # Generate LLM response if requested
    llm_response = None
    if args.use_llm:
        if not AZURE_LLM_AVAILABLE:
            print("⚠️ Azure LLM not available, skipping LLM response")
        else:
            print("\n🤖 Generating LLM response with context...")
            try:
                llm_client = LLMClient(
                    token_manager=None,
                    user_sid=args.user_sid,
                    cert_path=args.azure_cert_path,
                    config_path=azure_config_path
                )
                llm_response = llm_client.generate_response(
                    query=args.query,
                    context=results,
                    stream=not args.no_stream
                )
                print("✅ LLM response generated")
            except Exception as e:
                print(f"⚠️ Failed to generate LLM response: {e}")
                import traceback
                print(traceback.format_exc())
    
    # Build graph visualization
    nodes = []
    edges = []
    seen = set()
    
    # Add result nodes
    for res in results:
        chunk_id = res.get('chunk_id', res['id'])
        node_id = f"chunk_{chunk_id}"
        nodes.append({
            'id': node_id,
            'label': res['fqn'],
            'fqn': res['fqn']
        })
        seen.add(node_id)
    
    # Load graph and find relationships
    if args.graph_file:
        graph_loader = StandaloneGraphLoader(args.graph_file)
        for res in results:
            chunk_id = res.get('chunk_id', res['id'])
            related = graph_loader.find_related(chunk_id, max_depth=args.graph_depth)
            
            for rel in related:
                nid = rel['chunk_id']
                if nid not in seen:
                    label = rel.get('fqn', rel.get('name', nid))
                    nodes.append({
                        'id': nid,
                        'label': label,
                        'fqn': rel.get('fqn', '')
                    })
                    seen.add(nid)
                
                source_node_id = f"chunk_{chunk_id}"
                edges.append({
                    'from': source_node_id,
                    'to': nid,
                    'relationship': rel['relationship']
                })
    
    # Generate HTML
    mermaid_snippet = mermaid_from_graph(nodes, edges)
    html_content = build_html(args.query, results, mermaid_snippet, llm_response)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Wrote report to {args.output}")


if __name__ == "__main__":
    main()
