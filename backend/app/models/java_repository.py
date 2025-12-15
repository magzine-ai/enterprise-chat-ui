"""Java Repository model for storing repository metadata."""
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from app.models.java_chunk import JavaChunk


class RepositoryIndexStatus(str, Enum):
    """Repository indexing status enumeration."""
    PENDING = "pending"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class JavaRepositoryBase(SQLModel):
    """Base Java repository schema."""
    name: str
    local_path: Optional[str] = None  # For local repositories
    github_url: Optional[str] = None  # For GitHub repositories
    github_branch: Optional[str] = "main"  # Branch to clone
    description: Optional[str] = None
    file_count: Optional[int] = None  # Total number of files indexed
    languages: Optional[str] = None  # JSON array of detected languages


class JavaRepository(JavaRepositoryBase, table=True):
    """Java repository database model."""
    __tablename__ = "java_repositories"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    status: RepositoryIndexStatus = Field(default=RepositoryIndexStatus.PENDING)
    last_indexed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    file_count: Optional[int] = None  # Total number of files indexed
    languages: Optional[str] = None  # JSON array of detected languages
    
    # Relationships
    chunks: list["JavaChunk"] = Relationship(back_populates="repository")


class JavaRepositoryCreate(JavaRepositoryBase):
    """Java repository creation schema."""
    pass


class JavaRepositoryRead(JavaRepositoryBase):
    """Java repository read schema."""
    id: int
    status: RepositoryIndexStatus
    last_indexed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    file_count: Optional[int] = None
    languages: Optional[str] = None

