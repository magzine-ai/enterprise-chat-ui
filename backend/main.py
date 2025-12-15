"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api import auth, conversations, jobs, websocket, splunk, java_code
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
app.include_router(java_code.router)


@app.on_event("startup")
async def startup_event():
    """Start background tasks on startup."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Validate SSO configuration if enabled
    from app.services.sso_service import sso_service
    if sso_service.is_enabled():
        is_valid, error = sso_service.validate_config()
        if not is_valid:
            logger.warning(f"SSO configuration is invalid: {error}")
            logger.warning("SSO will not function correctly. Please check your configuration.")
    
    # Load persisted graphs on startup
    logger.info("🔄 Loading persisted graphs on startup...")
    from app.services.graph_service import graph_service
    from app.core.database import engine
    from sqlmodel import Session, select
    from app.models.java_repository import JavaRepository
    
    with Session(engine) as session:
        # Get all repositories
        repositories = session.exec(select(JavaRepository)).all()
        
        # Try to load graph for each repository
        loaded_count = 0
        for repo in repositories:
            if graph_service.graph_exists(repository_id=repo.id):
                if graph_service.load_graph(repository_id=repo.id):
                    loaded_count += 1
                    logger.info(f"✅ Loaded graph for repository {repo.name} (ID: {repo.id})")
                else:
                    logger.warning(f"⚠️  Failed to load graph for repository {repo.name} (ID: {repo.id})")
        
        # Also try to load global graph if it exists
        if graph_service.graph_exists():
            if graph_service.load_graph():
                logger.info("✅ Loaded global graph")
            else:
                logger.warning("⚠️  Failed to load global graph")
        
        if loaded_count > 0:
            logger.info(f"✅ Loaded {loaded_count} repository graph(s) on startup")
        else:
            logger.info("ℹ️  No persisted graphs found. Graphs will be built on demand.")
    
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

