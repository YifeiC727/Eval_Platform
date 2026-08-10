from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.comparator import compare_and_adjudicate, resolve_with_third, get_disagreed_checkpoints
from app.models import Assignment, Video, Question, User
import random

router = APIRouter(prefix="/api/arbitration", tags=["arbitration"])


@router.post("/compare/{video_id}")
def trigger_comparison(video_id: int, db: Session = Depends(get_db)):
    return compare_and_adjudicate(db, video_id)


@router.post("/assign-third/{video_id}")
def assign_third_person(video_id: int, db: Session = Depends(get_db)):
    disagreed = get_disagreed_checkpoints(db, video_id)
    if not disagreed:
        return {"status": "no disagreements"}

    existing_third = db.query(Assignment).filter(
        Assignment.video_id == video_id,
        Assignment.role == "third",
    ).first()
    if existing_third:
        return {"status": "already assigned", "assignment_id": existing_third.id}

    a_assign = db.query(Assignment).filter(
        Assignment.video_id == video_id, Assignment.role == "A"
    ).first()
    b_assign = db.query(Assignment).filter(
        Assignment.video_id == video_id, Assignment.role == "B"
    ).first()

    exclude_ids = set()
    if a_assign:
        exclude_ids.add(a_assign.annotator_id)
    if b_assign:
        exclude_ids.add(b_assign.annotator_id)

    candidates = db.query(User).filter(
        User.role == "annotator",
        User.id.notin_(exclude_ids),
    ).all()

    if not candidates:
        return {"error": "no available annotators"}

    third_person = random.choice(candidates)
    assignment = Assignment(
        video_id=video_id,
        annotator_id=third_person.id,
        role="third",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "status": "assigned",
        "assignment_id": assignment.id,
        "annotator": third_person.username,
        "disagreed_checkpoints": len(disagreed),
    }


@router.post("/resolve-third/{video_id}")
def trigger_third_resolution(video_id: int, db: Session = Depends(get_db)):
    return resolve_with_third(db, video_id)


@router.get("/status/{video_id}")
def get_arbitration_status(video_id: int, db: Session = Depends(get_db)):
    from app.models import FinalResult, Checkpoint

    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        return {"error": "video not found"}

    checkpoints = db.query(Checkpoint).filter(Checkpoint.question_id == video.question_id).all()
    finals = db.query(FinalResult).filter(FinalResult.video_id == video_id).all()
    final_map = {f.checkpoint_id: f for f in finals}

    assignments = db.query(Assignment).filter(Assignment.video_id == video_id).all()

    result = {
        "video_id": video.video_id,
        "total_checkpoints": len(checkpoints),
        "finalized": sum(1 for f in finals if f.method not in ("pending_third", "pending_expert")),
        "pending_third": sum(1 for f in finals if f.method == "pending_third"),
        "pending_expert": sum(1 for f in finals if f.method == "pending_expert"),
        "not_compared": len(checkpoints) - len(finals),
        "assignments": [
            {"role": a.role, "status": a.status, "annotator_id": a.annotator_id}
            for a in assignments
        ],
    }
    return result
