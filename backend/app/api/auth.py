"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from app.core.auth import verify_password, create_access_token
from app.core.database import get_session
from app.core.config import settings
from app.services.sso_service import sso_service
from datetime import timedelta
from typing import Annotated, Optional

router = APIRouter(prefix="/auth", tags=["auth"])

# Create OAuth2 scheme (always created, but auto_error=False makes it optional)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)

# TODO: Replace with real user database
DEV_USERS = {
    "dev": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # password: "dev"
}


def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(http_bearer)] = None,
    token: Annotated[Optional[str], Depends(oauth2_scheme)] = None,
) -> str:
    """
    Get current authenticated user from JWT token or SSO.
    Returns default user if authentication is disabled.
    """
    # Handle OPTIONS requests immediately (CORS preflight) - return before dependency evaluation
    if request.method == "OPTIONS":
        return settings.default_user
    
    # If authentication is disabled, return default user
    if not settings.auth_enabled:
        return settings.default_user
    
    # Try to get token from HTTPBearer first, then OAuth2
    auth_token = None
    if credentials and credentials.credentials:
        auth_token = credentials.credentials
    elif token:
        auth_token = token
    
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode and validate JWT token
    from app.core.auth import decode_access_token
    payload = decode_access_token(auth_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return username


@router.post("/login")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    Login endpoint. Returns JWT token.
    
    For development, use username="dev", password="dev"
    
    Note: This endpoint is only functional when auth_enabled=True.
    When SSO is enabled, use the SSO endpoints instead.
    """
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled. SSO may be enabled - check /auth/sso endpoints."
        )
    
    # TODO: Replace with database lookup
    hashed_password = DEV_USERS.get(form_data.username)
    if not hashed_password or not verify_password(form_data.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(current_user: Annotated[str, Depends(get_current_user)]):
    """Get current user info."""
    return {"username": current_user}


@router.get("/sso/authorize")
async def sso_authorize():
    """
    Get SSO authorization URL for OAuth2/OIDC providers.
    Returns URL to redirect user to for SSO login.
    """
    if not sso_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO is not enabled"
        )
    
    auth_url = sso_service.get_authorization_url()
    if not auth_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate SSO authorization URL"
        )
    
    return {"authorization_url": auth_url}


@router.get("/sso/callback")
async def sso_callback(code: str, state: Optional[str] = None):
    """
    OAuth2/OIDC callback endpoint.
    Handles the redirect from SSO provider after user authentication.
    """
    if not sso_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO is not enabled"
        )
    
    try:
        user_info = await sso_service.authenticate_oauth2(code, state)
        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SSO authentication failed"
            )
        
        # Create JWT token for the authenticated user
        username = user_info.get("username") or user_info.get("email") or "sso_user"
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": username, "sso": True, **user_info}, 
            expires_delta=access_token_expires
        )
        
        return {"access_token": access_token, "token_type": "bearer", "user": user_info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SSO authentication error: {str(e)}"
        )


@router.get("/sso/status")
async def sso_status():
    """Get SSO configuration status."""
    is_valid, error = sso_service.validate_config()
    return {
        "enabled": sso_service.is_enabled(),
        "provider": sso_service.provider,
        "valid": is_valid,
        "error": error
    }


