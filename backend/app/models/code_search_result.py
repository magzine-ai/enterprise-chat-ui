"""Code Search Result model for storing search metadata and results."""
from sqlmodel import SQLModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class CodeSearchResult(SQLModel, table=True):
    """Code search result database model for tracking search metadata."""
    __tablename__ = "code_search_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    query: str
    repository_id: Optional[int] = None
    chunk_id: Optional[int] = None
    
    # Search scores
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    graph_proximity: float = 0.0
    runtime_hits: float = 0.0
    confidence: float = 0.0
    
    # Final weighted score
    final_score: float = 0.0
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CodeSearchResultCreate(SQLModel):
    """Code search result creation schema."""
    query: str
    repository_id: Optional[int] = None
    chunk_id: Optional[int] = None
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    graph_proximity: float = 0.0
    runtime_hits: float = 0.0
    confidence: float = 0.0
    final_score: float = 0.0


class CodeSearchResultRead(SQLModel):
    """Code search result read schema."""
    id: int
    query: str
    repository_id: Optional[int]
    chunk_id: Optional[int]
    lexical_score: float
    semantic_score: float
    graph_proximity: float
    runtime_hits: float
    confidence: float
    final_score: float
    created_at: datetime

