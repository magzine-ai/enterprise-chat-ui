"""Job service for creating and managing async jobs."""
from sqlmodel import Session
from app.models.job import Job, JobStatus
from app.workers.chart_worker import generate_chart_data_async
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)

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
        
        logger.info(f"📝 Creating new job: type={job_type}, job_id={job_id}, params={params}")
        
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
        
        logger.info(f"✅ Job {job_id} created and saved to database with status QUEUED")
        
        # Start job as background task
        if job_type == "chart":
            logger.info(f"📊 Starting chart generation job {job_id}")
            asyncio.create_task(
                generate_chart_data_async(
                    job_id,
                    params.get("range", 30)
                )
            )
        elif job_type == "build_graph":
            from app.workers.graph_worker import build_graph_async
            repository_id = params.get("repository_id")
            rebuild = params.get("rebuild", False)
            if not repository_id:
                logger.error(f"❌ repository_id is required for build_graph job {job_id}")
                raise ValueError("repository_id is required for build_graph job")
            logger.info(f"🚀 Starting graph {'rebuild' if rebuild else 'build'} job {job_id} for repository {repository_id}")
            asyncio.create_task(
                build_graph_async(job_id, repository_id)
            )
        else:
            logger.error(f"❌ Unknown job type: {job_type} for job {job_id}")
            raise ValueError(f"Unknown job type: {job_type}")
        
        logger.info(f"✅ Job {job_id} background task started")
        return db_job


