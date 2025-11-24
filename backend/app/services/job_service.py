"""Job service for creating and managing async jobs."""
from sqlmodel import Session
from app.models.job import Job, JobStatus
from app.workers.chart_worker import generate_chart_data
from app.core.redis_client import redis_client
from rq import Queue
import uuid
import json

queue = Queue(connection=redis_client)


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
        """Create and enqueue a new job."""
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
        
        # Enqueue job in RQ
        if job_type == "chart":
            queue.enqueue(
                generate_chart_data,
                job_id,
                params.get("range", 30),
                job_id=job_id,
                job_timeout="5m"
            )
        else:
            # TODO: Support other job types
            raise ValueError(f"Unknown job type: {job_type}")
        
        return db_job


