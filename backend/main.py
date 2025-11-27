"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api import auth, conversations, jobs, websocket, splunk
from app.services.job_listener import listen_for_job_updates
import asyncio

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="Enterprise Chat API",
    description="Backend API for enterprise chat UI with async job processing",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(jobs.router)
app.include_router(websocket.router)
app.include_router(splunk.router)


@app.on_event("startup")
async def startup_event():
    """Start background tasks on startup."""
    # Validate SSO configuration if enabled
    from app.services.sso_service import sso_service
    if sso_service.is_enabled():
        is_valid, error = sso_service.validate_config()
        if not is_valid:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"SSO configuration is invalid: {error}")
            logger.warning("SSO will not function correctly. Please check your configuration.")
    
    # Start job update listener
    asyncio.create_task(listen_for_job_updates())


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Enterprise Chat API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/metrics")
async def metrics():
    """Metrics endpoint stub (for Prometheus)."""
    from app.services.websocket_manager import websocket_manager
    # TODO: Add actual Prometheus metrics
    return {
        "active_connections": len(websocket_manager.active_connections),
        "jobs_queued": 0  # In-memory event bus doesn't track queue size
    }

