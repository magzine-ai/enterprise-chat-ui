"""Tests for job worker."""
import pytest
import asyncio
from app.workers.chart_worker import generate_chart_data_async
from app.models.job import Job, JobStatus
from app.core.database import init_db, get_session
from sqlmodel import Session, select
import uuid

init_db()


@pytest.mark.asyncio
async def test_chart_worker():
    """Test chart data generation worker."""
    session = next(get_session())
    
    # Create test job
    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        type="chart",
        status=JobStatus.QUEUED
    )
    job.set_params({"range": 7})
    session.add(job)
    session.commit()
    session.refresh(job)
    
    # Run worker
    await generate_chart_data_async(job_id, range_days=7)
    
    # Verify job completed
    statement = select(Job).where(Job.job_id == job_id)
    updated_job = session.exec(statement).first()
    assert updated_job is not None
    assert updated_job.status == JobStatus.COMPLETED
    assert updated_job.progress == 100
    assert updated_job.get_result() is not None
    assert "dataset" in updated_job.get_result()


