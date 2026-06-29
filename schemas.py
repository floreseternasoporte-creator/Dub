from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum


class JobStatusEnum(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    error = "error"


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    error = "error"


class StepInfo(BaseModel):
    label: str
    status: StepStatus
    group: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class GroupInfo(BaseModel):
    label: str
    status: str


class JobCreate(BaseModel):
    target_languages: List[str] = ["es"]


class JobStatus(BaseModel):
    id: str
    filename: str
    status: JobStatusEnum
    progress: int = 0
    current_step: Optional[str] = None
    steps: Dict[str, StepInfo] = {}
    groups: Dict[str, GroupInfo] = {}
    error: Optional[str] = None
    outputs: Optional[Dict[str, str]] = None


class JobResponse(BaseModel):
    job_id: str
    filename: str


class LanguageOption(BaseModel):
    code: str
    name: str
    flag: str
