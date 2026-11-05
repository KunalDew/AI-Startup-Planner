import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Field, SQLModel, Session, create_engine, select
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv

import asyncio
import json
from fastapi.responses import StreamingResponse

import asyncio
import json
from fastapi.responses import StreamingResponse

# --- Database Setup & Models ---
load_dotenv(Path(__file__).resolve().parent / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"connect_timeout": 5},
)

class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    idea: str
    status: str = Field(default="processing")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # JSONB is native to Postgres and perfect for storing CrewAI's structured outputs
    final_report: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    intermediate_outputs: Optional[Dict[str, Any]] = Field(default={}, sa_column=Column(JSONB))
    error_message: Optional[str] = None

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Startup Report Generator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas for API Validation ---
class IdeaInput(BaseModel):
    idea: str

class JobResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# --- Background Worker ---
def execute_crew_job(job_id: str, raw_idea: str):
    """Runs asynchronously and opens its own DB session to save results."""
    with Session(engine) as session:
        job = session.exec(select(Job).where(Job.id == job_id)).first()
        if not job:
            return
        
        try:
            from flow import run_startup_workflow

            result = run_startup_workflow(raw_idea, job_id)
            if isinstance(result, BaseModel):
                serialized_result = result.model_dump(mode="json")
            elif isinstance(result, dict):
                serialized_result = result
            else:
                raise TypeError(
                    "CrewAI Flow returned an unsupported result type: "
                    f"{type(result).__name__}"
                )

            job.status = "completed"
            job.final_report = serialized_result
            session.add(job)
            session.commit()
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            session.add(job)
            session.commit()

# --- Endpoints ---
@app.post("/reports", response_model=JobResponse)
async def create_report_job(
    input_data: IdeaInput, 
    background_tasks: BackgroundTasks, 
    session: Session = Depends(get_session)
):
    # Create the job in Postgres
    new_job = Job(idea=input_data.idea)
    session.add(new_job)
    session.commit()
    session.refresh(new_job)
    
    # Dispatch execution to the background
    background_tasks.add_task(execute_crew_job, new_job.id, new_job.idea)
    
    return JobResponse(job_id=new_job.id, status=new_job.status)

@app.get("/reports/{job_id}", response_model=JobResponse)
async def get_report_status(job_id: str, session: Session = Depends(get_session)):
    job = session.exec(select(Job).where(Job.id == job_id)).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobResponse(
        job_id=job.id,
        status=job.status,
        result=job.final_report,
        error=job.error_message
    )

@app.get("/reports/{job_id}/stream")
async def stream_report_progress(job_id: str, session: Session = Depends(get_session)):
    """Streams job progress to the client using Server-Sent Events."""
    
    # Verify the job exists before opening the stream
    job = session.exec(select(Job).where(Job.id == job_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        last_step = 0
        while True:
            # Refresh job state from the database
            session.expire_all() 
            current_job = session.exec(select(Job).where(Job.id == job_id)).first()
            
            if not current_job:
                break

            # Count how many tasks have populated the intermediate_outputs JSONB column
            completed_tasks = len(current_job.intermediate_outputs or {})
            
            # Yield an update if progress has changed
            if completed_tasks > last_step:
                last_step = completed_tasks
                payload = {
                    "job_id": current_job.id,
                    "status": current_job.status,
                    "completed_agents": completed_tasks,
                    "total_agents": 6,
                    "message": f"Agent {completed_tasks + 1} of 6 is working..." if completed_tasks < 6 else "Finalizing..."
                }
                # SSE format requires the 'data: ' prefix and double newline
                yield f"data: {json.dumps(payload)}\n\n"

            # Check for terminal states
            if current_job.status in ["completed", "failed"]:
                terminal_payload = {
                    "job_id": current_job.id,
                    "status": current_job.status,
                    "completed_agents": completed_tasks,
                    "result": current_job.final_report if current_job.status == "completed" else None,
                    "error": current_job.error_message
                }
                yield f"data: {json.dumps(terminal_payload)}\n\n"
                break
                
            # Wait 2 seconds before checking the database again
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")