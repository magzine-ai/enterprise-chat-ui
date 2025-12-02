"""Splunk query execution endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from datetime import datetime
from app.api.auth import get_current_user
from app.core.database import get_session
from app.services.splunk_service import splunk_service
from app.models.splunk_query_result import SplunkQueryResult
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
    resultId: Optional[int] = None  # ID of stored result


@router.post("/execute", response_model=SplunkQueryResponse)
async def execute_splunk_query(
    request: SplunkQueryRequest,
    current_user: str = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Execute a Splunk query and return formatted results.
    Stores results in database and updates if query was previously executed.
    
    Executes the SPL query against Splunk, analyzes the results to determine
    the appropriate visualization type, stores the results in the database,
    and returns formatted data ready for frontend rendering.
    
    Args:
        request: Query request with SPL query string
        current_user: Current authenticated user (from dependency)
        session: Database session
    
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
        # Generate query hash for lookup
        query_hash = SplunkQueryResult.generate_query_hash(
            request.query,
            request.earliest_time,
            request.latest_time
        )
        
        # Check if result exists for this query
        statement = select(SplunkQueryResult).where(
            SplunkQueryResult.query_hash == query_hash,
            SplunkQueryResult.user_id == current_user
        )
        existing_result = session.exec(statement).first()
        
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
        
        # Store or update result in database
        if existing_result:
            # Update existing result
            existing_result.set_columns(formatted_result["columns"])
            existing_result.set_rows(formatted_result["rows"])
            existing_result.row_count = formatted_result["rowCount"]
            existing_result.execution_time = formatted_result.get("executionTime")
            existing_result.visualization_type = formatted_result.get("visualizationType")
            existing_result.set_visualization_config(formatted_result.get("visualizationConfig"))
            existing_result.single_value = formatted_result.get("singleValue")
            existing_result.gauge_value = formatted_result.get("gaugeValue")
            existing_result.set_chart_data(formatted_result.get("chartData"))
            existing_result.is_time_series = formatted_result.get("isTimeSeries")
            existing_result.allow_chart_type_switch = formatted_result.get("allowChartTypeSwitch")
            existing_result.splunk_job_id = splunk_result.get("job_id")
            existing_result.error = formatted_result.get("error")
            existing_result.updated_at = datetime.utcnow()
            
            session.add(existing_result)
            session.commit()
            session.refresh(existing_result)
            
            result_id = existing_result.id
        else:
            # Create new result
            new_result = SplunkQueryResult(
                query=request.query,
                query_hash=query_hash,
                user_id=current_user,
                earliest_time=request.earliest_time,
                latest_time=request.latest_time,
                row_count=formatted_result["rowCount"],
                execution_time=formatted_result.get("executionTime"),
                visualization_type=formatted_result.get("visualizationType"),
                single_value=formatted_result.get("singleValue"),
                gauge_value=formatted_result.get("gaugeValue"),
                is_time_series=formatted_result.get("isTimeSeries"),
                allow_chart_type_switch=formatted_result.get("allowChartTypeSwitch"),
                splunk_job_id=splunk_result.get("job_id"),
                error=formatted_result.get("error")
            )
            new_result.set_columns(formatted_result["columns"])
            new_result.set_rows(formatted_result["rows"])
            new_result.set_visualization_config(formatted_result.get("visualizationConfig"))
            new_result.set_chart_data(formatted_result.get("chartData"))
            
            session.add(new_result)
            session.commit()
            session.refresh(new_result)
            
            result_id = new_result.id
        
        # Add result ID to response
        formatted_result["resultId"] = result_id
        
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

