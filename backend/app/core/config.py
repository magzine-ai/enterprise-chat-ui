"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Authentication
    auth_enabled: bool = False  # Set to True to enable authentication
    default_user: str = "anonymous"  # Default user when auth is disabled
    
    # Security
    secret_key: str = "dev-secret-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # SSO Configuration (disabled by default)
    sso_enabled: bool = False
    sso_provider: Optional[str] = None  # "saml", "oauth2", "oidc"
    
    # SAML SSO Settings
    saml_entity_id: Optional[str] = None
    saml_metadata_url: Optional[str] = None
    saml_acs_url: Optional[str] = None
    saml_cert_path: Optional[str] = None
    saml_key_path: Optional[str] = None
    
    # OAuth2/OIDC SSO Settings
    oauth2_client_id: Optional[str] = None
    oauth2_client_secret: Optional[str] = None
    oauth2_authorization_url: Optional[str] = None
    oauth2_token_url: Optional[str] = None
    oauth2_userinfo_url: Optional[str] = None
    oauth2_redirect_uri: Optional[str] = None
    oauth2_scope: Optional[str] = "openid profile email"
    
    # Database
    database_url: str = "sqlite:///./data/chat.db"
    
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    # API Behavior
    mock_responses_enabled: bool = False  # Enable rich mock responses with blocks, charts, etc.
    
    # OpenAI Configuration
    openai_api_key: Optional[str] = None  # OpenAI API key (set via OPENAI_API_KEY env var)
    openai_model: str = "gpt-4"  # Model name to use (gpt-4, gpt-3.5-turbo, etc.)
    
    # Streaming Configuration
    streaming_enabled: bool = True  # Enable streaming responses when using LLM
    max_conversation_history: int = 10  # Number of messages to include in LLM context
    
    # AWS OpenSearch Configuration
    opensearch_host: Optional[str] = None  # OpenSearch cluster endpoint (e.g., "search-domain.us-east-1.es.amazonaws.com")
    opensearch_index: Optional[str] = None  # Index name for document storage
    opensearch_region: str = "us-east-1"  # AWS region
    opensearch_use_aws_auth: bool = True  # Use AWS authentication (requires boto3 credentials)
    opensearch_username: Optional[str] = None  # Basic auth username (for local dev)
    opensearch_password: Optional[str] = None  # Basic auth password (for local dev)
    opensearch_use_ssl: bool = True  # Use SSL for OpenSearch connection
    opensearch_verify_certs: bool = True  # Verify SSL certificates
    opensearch_use_vector_search: bool = True  # Enable vector similarity search
    opensearch_context_top_k: int = 3  # Number of documents to retrieve for context
    
    # Splunk Configuration
    splunk_host: Optional[str] = None  # Splunk instance hostname or IP
    splunk_port: int = 8089  # Splunk management port
    splunk_username: Optional[str] = None  # Splunk username
    splunk_password: Optional[str] = None  # Splunk password
    splunk_verify_ssl: bool = True  # Verify SSL certificates for Splunk connection
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


