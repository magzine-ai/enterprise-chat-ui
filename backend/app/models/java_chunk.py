"""Java Chunk model for storing code chunks with metadata."""
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import json

if TYPE_CHECKING:
    from app.models.java_repository import JavaRepository


class ChunkType(str, Enum):
    """Chunk type enumeration."""
    METHOD = "method"
    CLASS = "class"
    FILE = "file"
    MODULE = "module"


class JavaChunkBase(SQLModel):
    """Base Java chunk schema."""
    type: str  # "method" | "class" | "file" | "module"
    fqn: str  # Fully qualified name
    file_path: str
    start_line: int
    end_line: int
    code: str
    summary: Optional[str] = None
    
    # Stored as JSON strings
    imports: Optional[str] = None  # JSON array
    annotations: Optional[str] = None  # JSON array
    callers: Optional[str] = None  # JSON array
    callees: Optional[str] = None  # JSON array
    implemented_interfaces: Optional[str] = None  # JSON array
    extended_class: Optional[str] = None
    test_references: Optional[str] = None  # JSON array
    
    repository_id: int = Field(foreign_key="java_repositories.id")
    last_modified: Optional[datetime] = None


class JavaChunk(JavaChunkBase, table=True):
    """Java chunk database model."""
    __tablename__ = "java_chunks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship
    repository: Optional["JavaRepository"] = Relationship(back_populates="chunks")
    
    def get_imports(self) -> List[str]:
        """Parse imports JSON."""
        if not self.imports:
            return []
        return json.loads(self.imports)
    
    def set_imports(self, imports: List[str]):
        """Serialize imports to JSON."""
        self.imports = json.dumps(imports)
    
    def get_annotations(self) -> List[str]:
        """Parse annotations JSON."""
        if not self.annotations:
            return []
        return json.loads(self.annotations)
    
    def set_annotations(self, annotations: List[str]):
        """Serialize annotations to JSON."""
        self.annotations = json.dumps(annotations)
    
    def get_callers(self) -> List[str]:
        """Parse callers JSON."""
        if not self.callers:
            return []
        return json.loads(self.callers)
    
    def set_callers(self, callers: List[str]):
        """Serialize callers to JSON."""
        self.callers = json.dumps(callers)
    
    def get_callees(self) -> List[str]:
        """Parse callees JSON."""
        if not self.callees:
            return []
        return json.loads(self.callees)
    
    def set_callees(self, callees: List[str]):
        """Serialize callees to JSON."""
        self.callees = json.dumps(callees)
    
    def get_implemented_interfaces(self) -> List[str]:
        """Parse implemented interfaces JSON."""
        if not self.implemented_interfaces:
            return []
        return json.loads(self.implemented_interfaces)
    
    def set_implemented_interfaces(self, interfaces: List[str]):
        """Serialize implemented interfaces to JSON."""
        self.implemented_interfaces = json.dumps(interfaces)
    
    def get_test_references(self) -> List[str]:
        """Parse test references JSON."""
        if not self.test_references:
            return []
        return json.loads(self.test_references)
    
    def set_test_references(self, test_refs: List[str]):
        """Serialize test references to JSON."""
        self.test_references = json.dumps(test_refs)


class JavaChunkCreate(SQLModel):
    """Java chunk creation schema."""
    type: str
    fqn: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    summary: Optional[str] = None
    imports: Optional[List[str]] = None
    annotations: Optional[List[str]] = None
    callers: Optional[List[str]] = None
    callees: Optional[List[str]] = None
    implemented_interfaces: Optional[List[str]] = None
    extended_class: Optional[str] = None
    test_references: Optional[List[str]] = None
    repository_id: int
    last_modified: Optional[datetime] = None


class JavaChunkRead(SQLModel):
    """Java chunk read schema."""
    id: int
    type: str
    fqn: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    summary: Optional[str] = None
    imports: List[str]
    annotations: List[str]
    callers: List[str]
    callees: List[str]
    implemented_interfaces: List[str]
    extended_class: Optional[str] = None
    test_references: List[str]
    repository_id: int
    last_modified: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

