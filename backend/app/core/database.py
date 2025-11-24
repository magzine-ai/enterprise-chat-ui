"""Database connection and session management."""
from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

# Create engine
engine = create_engine(settings.database_url, echo=False)


def init_db():
    """Initialize database tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session


