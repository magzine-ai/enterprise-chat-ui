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
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


