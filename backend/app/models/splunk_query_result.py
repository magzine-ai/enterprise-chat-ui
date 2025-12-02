"""Splunk Query Result model for storing executed query results."""
from sqlmodel import SQLModel, Field
from typing import Optional, Any
from datetime import datetime
import json
import hashlib


class SplunkQueryResultBase(SQLModel):
    """Base Splunk query result schema."""
    query: str  # The SPL query
    query_hash: str  # Hash of query for quick lookup
    user_id: str  # User who executed the query
    earliest_time: Optional[str] = None
    latest_time: Optional[str] = None
    
    # Result data (stored as JSON)
    columns: Optional[str] = None  # JSON array of column names
    rows: Optional[str] = None  # JSON array of row data
    row_count: int = 0
    execution_time: Optional[float] = None
    
    # Visualization metadata
    visualization_type: Optional[str] = None
    visualization_config: Optional[str] = None  # JSON
    single_value: Optional[float] = None
    gauge_value: Optional[float] = None
    chart_data: Optional[str] = None  # JSON
    is_time_series: Optional[bool] = None
    allow_chart_type_switch: Optional[bool] = None
    
    # Splunk job info
    splunk_job_id: Optional[str] = None
    error: Optional[str] = None


class SplunkQueryResult(SplunkQueryResultBase, table=True):
    """Splunk query result database model."""
    __tablename__ = "splunk_query_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_columns(self) -> list[str]:
        """Parse columns JSON."""
        if not self.columns:
            return []
        return json.loads(self.columns)
    
    def set_columns(self, columns: list[str]):
        """Serialize columns to JSON."""
        self.columns = json.dumps(columns)
    
    def get_rows(self) -> list[list[Any]]:
        """Parse rows JSON."""
        if not self.rows:
            return []
        return json.loads(self.rows)
    
    def set_rows(self, rows: list[list[Any]]):
        """Serialize rows to JSON."""
        self.rows = json.dumps(rows)
    
    def get_visualization_config(self) -> Optional[dict[str, Any]]:
        """Parse visualization config JSON."""
        if not self.visualization_config:
            return None
        return json.loads(self.visualization_config)
    
    def set_visualization_config(self, config: Optional[dict[str, Any]]):
        """Serialize visualization config to JSON."""
        self.visualization_config = json.dumps(config) if config else None
    
    def get_chart_data(self) -> Optional[list[dict[str, Any]]]:
        """Parse chart data JSON."""
        if not self.chart_data:
            return None
        return json.loads(self.chart_data)
    
    def set_chart_data(self, data: Optional[list[dict[str, Any]]]):
        """Serialize chart data to JSON."""
        self.chart_data = json.dumps(data) if data else None
    
    @staticmethod
    def generate_query_hash(query: str, earliest_time: Optional[str] = None, latest_time: Optional[str] = None) -> str:
        """Generate hash for query lookup."""
        query_str = f"{query}|{earliest_time or ''}|{latest_time or ''}"
        return hashlib.sha256(query_str.encode()).hexdigest()


class SplunkQueryResultCreate(SQLModel):
    """Splunk query result creation schema."""
    query: str
    earliest_time: Optional[str] = None
    latest_time: Optional[str] = None


class SplunkQueryResultRead(SQLModel):
    """Splunk query result read schema."""
    id: int
    query: str
    query_hash: str
    user_id: str
    earliest_time: Optional[str] = None
    latest_time: Optional[str] = None
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time: Optional[float] = None
    visualization_type: Optional[str] = None
    visualization_config: Optional[dict[str, Any]] = None
    single_value: Optional[float] = None
    gauge_value: Optional[float] = None
    chart_data: Optional[list[dict[str, Any]]] = None
    is_time_series: Optional[bool] = None
    allow_chart_type_switch: Optional[bool] = None
    splunk_job_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

