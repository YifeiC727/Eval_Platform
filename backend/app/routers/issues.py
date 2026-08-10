from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import Assignment, Annotation, Video, Question, Checkpoint, User, FinalResult

router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.post("/report")
def report_issue(data: dict, db: Session = Depends(get_db)):
    """标注员上报技术无效（视频打不开/黑屏/损坏等）"""
    assignment_id = data.get("assignment_id")
    issue_type = data.get("issue_type", "技术无效")
    description = data.get("description", "")

    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(404, "assignment not found")

    from app.models import Base
    from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
    # Store in a simple way - add to assignment note or create issue record
    # For now, mark the assignment status and store the issue
    assignment.status = "issue_reported"

    db.commit()
    return {
        "status": "reported",
        "message": f"已上报: {issue_type} - {description}",
        "assignment_id": assignment_id,
    }


@router.get("/list")
def list_issues(project_id: int = None, db: Session = Depends(get_db)):
    """管理员查看所有技术无效上报"""
    query = db.query(Assignment).filter(Assignment.status == "issue_reported")
    if project_id:
        query = query.join(Video).join(Question).filter(Question.project_id == project_id)

    assignments = query.all()
    result = []
    for a in assignments:
        video = a.video
        question = video.question if video else None
        annotator = a.annotator
        result.append({
            "assignment_id": a.id,
            "video_id": video.video_id if video else "",
            "question_id": question.question_id if question else "",
            "annotator": annotator.display_name if annotator else "",
            "role": a.role,
            "reported_at": a.submitted_at.isoformat() if a.submitted_at else None,
        })
    return result


@router.post("/resolve/{assignment_id}")
def resolve_issue(assignment_id: int, data: dict, db: Session = Depends(get_db)):
    """管理员处理技术无效：重新分配或标记无效"""
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(404, "assignment not found")

    action = data.get("action", "reassign")
    if action == "invalidate":
        assignment.status = "invalidated"
    elif action == "reassign":
        assignment.status = "pending"
    db.commit()
    return {"status": "resolved", "action": action}
