from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.services.comparator import compare_and_adjudicate, resolve_with_third, get_disagreed_checkpoints
from app.models import Assignment, Video, Question, User, EvalBatch

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
        User.role.contains("annotator"),
        User.id.notin_(exclude_ids),
    ).all()

    if not candidates:
        return {"error": "no available annotators"}

    # 选当前任务数最少的人，避免负载不均
    def task_count(user):
        return db.query(func.count(Assignment.id)).filter(Assignment.annotator_id == user.id).scalar()

    third_person = min(candidates, key=task_count)
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


@router.post("/assign-third-batch/{batch_id}")
def assign_third_batch(batch_id: int, annotator_id: int = None, db: Session = Depends(get_db)):
    """批量为批次内有分歧但无第三人的视频分配仲裁人。
    If annotator_id is given, assign that specific person to all.
    Otherwise pick from batch annotators with lowest load, excluding A/B per video.
    """
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        return {"error": "batch not found"}

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    assigned = 0

    for video in videos:
        a_assign = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.role == "A", Assignment.status == "submitted"
        ).first()
        b_assign = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.role == "B", Assignment.status == "submitted"
        ).first()
        if not a_assign or not b_assign:
            continue

        existing_third = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.role == "third"
        ).first()
        if existing_third:
            continue

        disagreed = get_disagreed_checkpoints(db, video.id)
        if not disagreed:
            continue

        exclude_ids = {a_assign.annotator_id, b_assign.annotator_id}

        if annotator_id and annotator_id not in exclude_ids:
            third_id = annotator_id
        else:
            candidates = db.query(User).filter(
                User.role.contains("annotator"),
                User.id.notin_(exclude_ids),
            ).all()
            if not candidates:
                continue
            def task_count(user):
                return db.query(func.count(Assignment.id)).filter(
                    Assignment.annotator_id == user.id, Assignment.role == "third"
                ).scalar()
            third_person = min(candidates, key=task_count)
            third_id = third_person.id

        db.add(Assignment(video_id=video.id, annotator_id=third_id, role="third"))
        assigned += 1

    db.commit()
    return {"status": "assigned", "count": assigned}


@router.post("/assign-third-single")
def assign_third_single(data: dict, db: Session = Depends(get_db)):
    """为单个视频分配第三人"""
    video_db_id = data.get("video_db_id")
    annotator_id = data.get("annotator_id")

    if not video_db_id or not annotator_id:
        return {"error": "video_db_id and annotator_id required"}

    existing = db.query(Assignment).filter(
        Assignment.video_id == video_db_id, Assignment.role == "third"
    ).first()
    if existing:
        return {"error": "third already assigned", "annotator_id": existing.annotator_id}

    db.add(Assignment(video_id=video_db_id, annotator_id=annotator_id, role="third"))
    db.commit()
    return {"status": "assigned"}
