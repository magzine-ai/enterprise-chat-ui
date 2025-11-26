"""Job model for async task processing."""
from sqlmodel import SQLModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum
import json


class JobStatus(str, Enum):
    """Job status enumeration."""
    QUEUED = "queued"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"


class JobBase(SQLModel):
    """Base job schema."""
    type: str  # "chart", "plugin", etc.
    params: Optional[str] = None  # JSON string
    conversation_id: Optional[int] = None
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0  # 0-100
    result: Optional[str] = None  # JSON string
    error: Optional[str] = None


class Job(JobBase, table=True):
    """Job database model."""
    __tablename__ = "jobs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True)  # Unique job identifier
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_params(self) -> dict[str, Any]:
        """Parse params JSON."""
        if not self.params:
            return {}
        return json.loads(self.params)
    
    def set_params(self, params: dict[str, Any]):
        """Serialize params to JSON."""
        self.params = json.dumps(params)
    
    def get_result(self) -> Optional[dict[str, Any]]:
        """Parse result JSON."""
        if not self.result:
            return None
        return json.loads(self.result)
    
    def set_result(self, result: dict[str, Any]):
        """Serialize result to JSON."""
        self.result = json.dumps(result)


class JobCreate(SQLModel):
    """Job creation schema."""
    type: str
    params: Optional[dict[str, Any]] = None
    conversation_id: Optional[int] = None


class JobRead(JobBase):
    """Job read schema."""
    id: int
    job_id: str
    created_at: datetime
    updated_at: datetime
    params: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None


