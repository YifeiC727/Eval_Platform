from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    username: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "annotator"


class UserOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str]
    role: str

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    project_id: str
    name: str
    model_version: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    project_id: str
    name: str
    model_version: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class CheckpointOut(BaseModel):
    id: int
    checkpoint_id: str
    seq: Optional[int]
    text: str
    min_success_line: Optional[str]
    ability_id: Optional[str]
    ability_name: Optional[str]
    tag_id: Optional[str]
    tag_name: Optional[str]
    evidence_period: Optional[str]

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    id: int
    question_id: str
    prompt: str
    language: Optional[str]
    preprocess_note: Optional[str]
    checkpoint_count: int = 0

    class Config:
        from_attributes = True


class VideoOut(BaseModel):
    id: int
    video_id: str
    question_id: int
    model_version: Optional[str]
    oss_url: Optional[str]
    duration_sec: Optional[float]
    status: str

    class Config:
        from_attributes = True


class AssignmentOut(BaseModel):
    id: int
    video_id: int
    annotator_id: int
    role: str
    status: str
    assigned_at: datetime
    video: Optional[VideoOut] = None

    class Config:
        from_attributes = True


class AnnotationSubmit(BaseModel):
    checkpoint_id: int
    score: str
    fail_code: Optional[str] = None
    evidence_ts: Optional[str] = None
    note: Optional[str] = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if v not in ("C", "R", "N"):
            raise ValueError("score must be C, R, or N")
        return v

    @field_validator("fail_code")
    @classmethod
    def validate_fail_code(cls, v, info):
        score = info.data.get("score")
        if score == "C" and v:
            raise ValueError("C must not have a fail_code")
        if score in ("R", "N") and not v:
            raise ValueError("R/N must have a fail_code")
        if v and v not in [f"F{i:02d}" for i in range(1, 12)]:
            raise ValueError("fail_code must be F01-F11")
        return v


class BatchAnnotationSubmit(BaseModel):
    assignment_id: int
    annotations: list[AnnotationSubmit]


class FinalResultOut(BaseModel):
    id: int
    video_id: int
    checkpoint_id: int
    final_score: str
    final_fail_code: Optional[str]
    method: str
    note: Optional[str]

    class Config:
        from_attributes = True


class AbilityScoreOut(BaseModel):
    ability_id: str
    ability_name: str
    score: float
    c_count: int
    r_count: int
    n_count: int
    total_n: int
    coverage_status: str


class AssignmentCreate(BaseModel):
    video_id: int
    annotator_id: int
    role: str
