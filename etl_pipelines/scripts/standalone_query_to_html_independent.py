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

# Azure OpenAI for LLM (chat client)
try:
    from langchain_openai import AzureChatOpenAI
    from azure.identity import CertificateCredential
    from azure.core.exceptions import ClientAuthenticationError
    AZURE_LLM_AVAILABLE = True
except ImportError:
    AZURE_LLM_AVAILABLE = False
    print("⚠️ Azure LLM not available. Install: pip install langchain-openai azure-identity (optional, for LLM responses)")

# Azure OpenAI for LLM (chat client)
try:
    from langchain_openai import AzureChatOpenAI
    from azure.identity import CertificateCredential
    from azure.core.exceptions import ClientAuthenticationError
    AZURE_LLM_AVAILABLE = True
except ImportError:
    AZURE_LLM_AVAILABLE = False
    print("⚠️ Azure LLM not available. Install: pip install langchain-openai azure-identity (optional, for LLM responses)")


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
        embedding_model: str = "text-embedding-3-small"
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
        """
        self.host = host
        self.index = index
        self.client = None
        self.openai_client = None
        self.embedding_model = embedding_model
        
        # Load config
        if config_path is None:
            current_dir = os.path.dirname(__file__)
            config_path = os.path.join(current_dir, "config.ini")
        
        if os.path.exists(config_path):
            self.config = configparser.ConfigParser()
            self.config.read(config_path)
            print(f"✅ Loaded config from {config_path}")
            
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
                # AWS Auth
                aws_session = session.Session()
                credentials = aws_session.get_credentials()
                
                # Extract hostname from endpoint
                aws_host = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')[0]
                
                awsauth = AWSRequestsAuth(
                    credentials=credentials,
                    aws_host=aws_host,
                    aws_region=self.region,
                    aws_service='es'
                )
                
                # Determine port
                port = 443
                if ':' in self.opensearch_endpoint:
                    port_part = self.opensearch_endpoint.split(':')[-1].split('/')[0]
                    try:
                        port = int(port_part)
                    except ValueError:
                        port = 443
                
                hostname = aws_host
                
                self.client = OpenSearch(
                    hosts=[{'host': hostname, 'port': port}],
                    http_auth=awsauth,
                    use_ssl=use_ssl,
                    verify_certs=verify_certs,
                    connection_class=RequestsHttpConnection
                )
                print(f"✅ Connected to AWS OpenSearch: {self.opensearch_endpoint}")
            else:
                # Basic authentication (for local development)
                host_parts = self.opensearch_endpoint.replace('https://', '').replace('http://', '').split(':')
                hostname = host_parts[0]
                port = int(host_parts[1]) if len(host_parts) > 1 else 9200
                
                self.client = OpenSearch(
                    hosts=[{'host': hostname, 'port': port}],
                    use_ssl=use_ssl,
                    verify_certs=verify_certs,
                    connection_class=RequestsHttpConnection
                )
                print(f"✅ Connected to OpenSearch: {self.opensearch_endpoint}")
        except Exception as e:
            print(f"⚠️ Failed to connect to OpenSearch: {e}")
            import traceback
            print(traceback.format_exc())
        
        # Initialize OpenAI client for semantic search
        if openai_api_key and OPENAI_AVAILABLE:
            self.openai_client = OpenAI(api_key=openai_api_key)
            print("✅ OpenAI client initialized for semantic search")
    
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
            
            if use_semantic and self.openai_client:
                # Generate embedding for semantic search
                try:
                    response = self.openai_client.embeddings.create(
                        model=self.embedding_model,
                        input=query
                    )
                    query_embedding = response.data[0].embedding
                    
                    # Build kNN query
                    knn_query = {
                        "field": "embedding",
                        "query_vector": query_embedding,
                        "k": top_k,
                        "num_candidates": top_k * 2
                    }
                    
                    # Add filters
                    filters = []
                    if application_name:
                        filters.append({"term": {"application_name": application_name}})
                    if seal_id:
                        filters.append({"term": {"seal_id": seal_id}})
                    
                    if filters:
                        knn_query["filter"] = {"bool": {"must": filters}}
                    
                    query_body["query"] = {"match_all": {}}
                    query_body["knn"] = knn_query
                except Exception as e:
                    print(f"⚠️ Semantic search failed, falling back to text search: {e}")
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
            
            response = self.client.search(
                index=self.index_name,
                body=query_body
            )
            
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
            return None
        
        config = configparser.ConfigParser()
        config.read(config_path)
        return config
    
    def _refresh_token(self):
        """Obtain or refresh access token."""
        if not self.config or 'azure_openai' not in self.config:
            return None
        
        try:
            # Find certificate file
            if self.cert_path is None:
                current_dir = os.path.dirname(__file__)
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
                        print("⚠️ Certificate file not found")
                        return None
            else:
                cert_path = self.cert_path
            
            credential = CertificateCredential(
                tenant_id=self.config['azure_openai']['azure_tenant_id'],
                client_id=self.config['azure_openai']['azure_client_id'],
                certificate_path=cert_path
            )
            
            self.access_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
            return self.access_token
        except Exception as e:
            print(f"⚠️ Failed to obtain access token: {e}")
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
            self.chat_client = AzureChatOpenAI(
                azure_endpoint=self.config['azure_openai'].get('azure_endpoint', 'https://llm-multitenancy-exp.jpmchase.net/ver2/'),
                openai_api_version=self.config['azure_openai'].get('openai_api_version', '2024-10-21'),
                deployment_name=self.config['azure_openai'].get('deployment_name', 'gpt-4'),
                openai_api_key=self.config['azure_openai'].get('openai_api_key', ''),
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
    parser.add_argument("--openai-api-key", help="OpenAI API key for semantic/vector search")
    parser.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model for semantic search")
    parser.add_argument("--use-semantic", action="store_true", help="Use semantic/vector search (requires --openai-api-key)")
    parser.add_argument("--graph-file", help="Graph pickle file (optional)")
    parser.add_argument("--output", required=True, help="Output HTML file")
    parser.add_argument("--max-results", type=int, default=10, help="Max search results")
    parser.add_argument("--graph-depth", type=int, default=2, help="Graph traversal depth")
    
    # LLM arguments
    parser.add_argument("--use-llm", action="store_true", help="Generate LLM response with context from search results")
    parser.add_argument("--llm-config", help="Path to config.ini file for LLM configuration (default: script directory)")
    parser.add_argument("--llm-cert-path", help="Path to Azure certificate file (.pem)")
    parser.add_argument("--user-sid", default="default_user", help="User session ID for LLM (default: default_user)")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming for LLM response")
    args = parser.parse_args()
    
    # Validate arguments
    if not args.opensearch_host and not args.opensearch_config:
        parser.error("Either --opensearch-host or --opensearch-config is required")
    
    if args.use_semantic and not args.openai_api_key:
        parser.error("--openai-api-key is required when using --use-semantic")
    
    # Search
    searcher = StandaloneSearcher(
        host=args.opensearch_host,
        index=args.opensearch_index,
        config_path=args.opensearch_config,
        use_aws_auth=args.opensearch_use_aws_auth,
        region=args.opensearch_region,
        use_ssl=args.opensearch_use_ssl,
        verify_certs=args.opensearch_verify_certs,
        openai_api_key=args.openai_api_key,
        embedding_model=args.embedding_model
    )
    
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
                    cert_path=args.llm_cert_path,
                    config_path=args.llm_config
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
