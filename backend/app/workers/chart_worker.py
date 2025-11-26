"""Chart data generation worker."""
from sqlmodel import Session, select
from app.models.job import Job, JobStatus
from app.core.database import engine
from app.core.event_bus import event_bus
import asyncio
import random


async def generate_chart_data_async(job_id: str, range_days: int = 30):
    """
    Generate chart dataset (simulates long-running job).
    
    Publishes progress updates via event bus and WebSocket.
    """
    with Session(engine) as session:
        # Get job
        statement = select(Job).where(Job.job_id == job_id)
        job = session.exec(statement).first()
        if not job:
            return
        
        # Update status to started
        job.status = JobStatus.STARTED
        job.progress = 0
        session.add(job)
        session.commit()
        
        # Broadcast start
        await _broadcast_job_update(job_id, job.status, 0)
        
        # Simulate work with progress updates
        steps = 10
        for i in range(1, steps + 1):
            await asyncio.sleep(0.5)  # Simulate work
            progress = int((i / steps) * 100)
            
            job.progress = progress
            job.status = JobStatus.PROGRESS
            session.add(job)
            session.commit()
            
            await _broadcast_job_update(job_id, job.status, progress)
        
        # Generate chart data
        data_points = []
        for day in range(range_days):
            data_points.append({
                "date": f"2024-01-{day+1:02d}",
                "value": random.randint(10, 100)
            })
        
        result = {
            "type": "chart",
            "dataset": data_points,
            "blocks": [
                {
                    "type": "chart",
                    "data": {
                        "chartId": f"chart_{job_id}",
                        "dataset": data_points
                    }
                }
            ]
        }
        
        # Update job with result
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.set_result(result)
        session.add(job)
        session.commit()
        
        # Broadcast completion
        await _broadcast_job_update(job_id, job.status, 100, result)


async def _broadcast_job_update(job_id: str, status: str, progress: int, result: dict | None = None):
    """Broadcast job update via event bus."""
    message = {
        "type": "job.update",
        "data": {
            "job_id": job_id,
            "status": status,
            "progress": progress
        }
    }
    if result:
        message["data"]["result"] = result
    
    # Publish to event bus
    await event_bus.publish_json("job_updates", message)


