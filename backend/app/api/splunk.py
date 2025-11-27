"""Splunk query execution endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.api.auth import get_current_user
from app.services.splunk_service import splunk_service
import asyncio

router = APIRouter(prefix="/splunk", tags=["splunk"])


class SplunkQueryRequest(BaseModel):
    """Request model for Splunk query execution."""
    query: str
    earliest_time: Optional[str] = None
    latest_time: Optional[str] = None
    language: str = "spl"  # For future SQL support


class SplunkQueryResponse(BaseModel):
    """Response model for Splunk query execution."""
    columns: list[str]
    rows: list[list[Any]]
    rowCount: int
    executionTime: Optional[float] = None
    visualizationType: Optional[str] = None
    visualizationConfig: Optional[Dict[str, Any]] = None
    singleValue: Optional[float] = None
    gaugeValue: Optional[float] = None
    chartData: Optional[list[Dict[str, Any]]] = None
    isTimeSeries: Optional[bool] = None
    allowChartTypeSwitch: Optional[bool] = None
    error: Optional[str] = None


@router.post("/execute", response_model=SplunkQueryResponse)
async def execute_splunk_query(
    request: SplunkQueryRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Execute a Splunk query and return formatted results.
    
    Executes the SPL query against Splunk, analyzes the results to determine
    the appropriate visualization type, and returns formatted data ready
    for frontend rendering.
    
    Args:
        request: Query request with SPL query string
        current_user: Current authenticated user (from dependency)
    
    Returns:
        SplunkQueryResponse: Formatted results with visualization metadata
    
    Raises:
        HTTPException: If Splunk is not configured or query execution fails
    
    Visualization Types:
        - table: Standard data table
        - chart: Bar, line, pie, or area chart
        - single-value: Single numeric value display
        - gauge: Gauge/percentage display
    
    The visualization type is automatically determined based on:
        - Query commands (timechart, stats, etc.)
        - Result structure (number of rows, fields)
        - Presence of time fields
    """
    if not splunk_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Splunk service is not configured. Please set SPLUNK_HOST, SPLUNK_USERNAME, and SPLUNK_PASSWORD."
        )
    
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty"
        )
    
    try:
        # Execute query
        splunk_result = await splunk_service.execute_query(
            query=request.query,
            earliest_time=request.earliest_time,
            latest_time=request.latest_time
        )
        
        # Format result for frontend
        formatted_result = splunk_service.format_query_result(
            splunk_result=splunk_result,
            query=request.query
        )
        
        return SplunkQueryResponse(**formatted_result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except TimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Query execution timed out: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Error executing Splunk query: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute query: {str(e)}"
        )

