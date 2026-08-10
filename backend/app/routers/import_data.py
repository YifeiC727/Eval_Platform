import os
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, Question, Video
from app.services.importer import import_checkpoints_xlsx, import_video_list
from app.schemas import QuestionOut, CheckpointOut, VideoOut

router = APIRouter(prefix="/api/import", tags=["import"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/checkpoints")
async def upload_checkpoints(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "project not found")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        stats = import_checkpoints_xlsx(db, file_path, project_id)
    except Exception as e:
        raise HTTPException(400, f"import error: {e}")

    return {"status": "ok", **stats}


@router.post("/videos")
def upload_videos(
    project_id: int = Form(...),
    videos: list[dict] = [],
    db: Session = Depends(get_db),
):
    stats = import_video_list(db, videos, project_id)
    return {"status": "ok", **stats}


@router.post("/videos/batch")
def batch_create_videos(
    data: dict,
    db: Session = Depends(get_db),
):
    project_id = data.get("project_id")
    video_list = data.get("videos", [])

    if not project_id:
        raise HTTPException(400, "project_id required")

    stats = import_video_list(db, video_list, project_id)
    return {"status": "ok", **stats}


questions_router = APIRouter(prefix="/api/questions", tags=["questions"])


@questions_router.get("/", response_model=list[QuestionOut])
def list_questions(project_id: int = None, db: Session = Depends(get_db)):
    query = db.query(Question)
    if project_id:
        query = query.filter(Question.project_id == project_id)
    questions = query.all()
    result = []
    for q in questions:
        qo = QuestionOut(
            id=q.id,
            question_id=q.question_id,
            prompt=q.prompt,
            language=q.language,
            preprocess_note=q.preprocess_note,
            checkpoint_count=len(q.checkpoints),
        )
        result.append(qo)
    return result


@questions_router.get("/{question_id}/checkpoints", response_model=list[CheckpointOut])
def get_checkpoints(question_id: int, db: Session = Depends(get_db)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "question not found")
    return q.checkpoints


videos_router = APIRouter(prefix="/api/videos", tags=["videos"])


@videos_router.get("/", response_model=list[VideoOut])
def list_videos(project_id: int = None, db: Session = Depends(get_db)):
    query = db.query(Video)
    if project_id:
        from app.models import Question
        query = query.join(Question).filter(Question.project_id == project_id)
    return query.all()
