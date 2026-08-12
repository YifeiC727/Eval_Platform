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

    assignment.status = "issue_reported"
    db.commit()

    # Check if this triggers downstream logic
    video_id = assignment.video_id
    a_assign = db.query(Assignment).filter(Assignment.video_id == video_id, Assignment.role == "A").first()
    b_assign = db.query(Assignment).filter(Assignment.video_id == video_id, Assignment.role == "B").first()
    third_assign = db.query(Assignment).filter(Assignment.video_id == video_id, Assignment.role == "third").first()

    # If reporter is A/B and the other side is done → finalize
    if assignment.role in ("A", "B"):
        other = b_assign if assignment.role == "A" else a_assign
        if other and other.status == "submitted":
            # Other submitted normally → use other's annotations as final
            anns = db.query(Annotation).filter(Annotation.assignment_id == other.id).all()
            for ann in anns:
                existing = db.query(FinalResult).filter(
                    FinalResult.video_id == video_id, FinalResult.checkpoint_id == ann.checkpoint_id).first()
                if not existing:
                    db.add(FinalResult(
                        video_id=video_id, checkpoint_id=ann.checkpoint_id,
                        final_score=ann.score, final_fail_code=ann.fail_code, method="single"))
            db.commit()
        elif other and other.status == "issue_reported":
            # Both A/B invalid → third sees all (activation handled by /my visibility)
            pass

    # If reporter is third → assign expert
    if assignment.role == "third":
        existing_expert = db.query(Assignment).filter(
            Assignment.video_id == video_id, Assignment.role == "expert").first()
        if not existing_expert:
            db.add(Assignment(video_id=video_id, annotator_id=1, role="expert"))
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


@router.post("/drop/{video_db_id}")
def drop_video(video_db_id: int, db: Session = Depends(get_db)):
    """管理员确认视频技术无效，整题废弃不计入统计"""
    from app.models import Video as VideoModel
    video = db.query(VideoModel).filter(VideoModel.id == video_db_id).first()
    if not video:
        raise HTTPException(404, "video not found")

    question = video.question
    checkpoints = db.query(Checkpoint).filter(Checkpoint.question_id == question.id).all()

    # Remove any existing FinalResults for this video
    db.query(FinalResult).filter(FinalResult.video_id == video_db_id).delete(synchronize_session=False)

    # Create "dropped" FinalResults for all checkpoints
    for cp in checkpoints:
        db.add(FinalResult(
            video_id=video_db_id,
            checkpoint_id=cp.id,
            final_score="X",
            method="dropped",
        ))

    # Mark expert assignment as done (if exists)
    expert = db.query(Assignment).filter(
        Assignment.video_id == video_db_id, Assignment.role == "expert"
    ).first()
    if expert:
        expert.status = "submitted"

    db.commit()
    return {"status": "dropped", "checkpoints": len(checkpoints)}
