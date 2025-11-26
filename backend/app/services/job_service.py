"""Job service for creating and managing async jobs."""
from sqlmodel import Session
from app.models.job import Job, JobStatus
from app.workers.chart_worker import generate_chart_data_async
import uuid
import asyncio

class JobService:
    """Service for job management."""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def create_job(
        self,
        job_type: str,
        params: dict,
        conversation_id: int | None = None
    ) -> Job:
        """Create and start a new async job."""
        job_id = str(uuid.uuid4())
        
        # Create job record
        db_job = Job(
            job_id=job_id,
            type=job_type,
            conversation_id=conversation_id,
            status=JobStatus.QUEUED
        )
        db_job.set_params(params)
        self.session.add(db_job)
        self.session.commit()
        self.session.refresh(db_job)
        
        # Start job as background task
        if job_type == "chart":
            asyncio.create_task(
                generate_chart_data_async(
                    job_id,
                    params.get("range", 30)
                )
            )
        else:
            # TODO: Support other job types
            raise ValueError(f"Unknown job type: {job_type}")
        
        return db_job


