"""Job endpoints for async task processing."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import Annotated
from app.core.database import get_session
from app.models.job import Job, JobCreate, JobRead, JobStatus
from app.api.auth import get_current_user
from app.services.job_service import JobService
import uuid

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead)
async def create_job(
    job: JobCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """
    Create a new async job.
    Returns job_id immediately; job will be processed by worker.
    """
    job_service = JobService(session)
    db_job = await job_service.create_job(
        job_type=job.type,
        params=job.params or {},
        conversation_id=job.conversation_id
    )
    
    return JobRead(
        id=db_job.id,
        job_id=db_job.job_id,
        type=db_job.type,
        status=db_job.status,
        progress=db_job.progress,
        conversation_id=db_job.conversation_id,
        created_at=db_job.created_at,
        updated_at=db_job.updated_at,
        params=db_job.get_params(),
        result=db_job.get_result()
    )


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[str, Depends(get_current_user)],
):
    """Get job status and result."""
    statement = select(Job).where(Job.job_id == job_id)
    job = session.exec(statement).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    return JobRead(
        id=job.id,
        job_id=job.job_id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        conversation_id=job.conversation_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        params=job.get_params(),
        result=job.get_result(),
        error=job.error
    )


