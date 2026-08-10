from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Assignment, Annotation
from app.schemas import BatchAnnotationSubmit
from app.services.comparator import compare_and_adjudicate

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


@router.post("/submit")
def submit_annotations(data: BatchAnnotationSubmit, db: Session = Depends(get_db)):
    assignment = db.query(Assignment).filter(Assignment.id == data.assignment_id).first()
    if not assignment:
        raise HTTPException(404, "assignment not found")
    if assignment.status == "submitted":
        raise HTTPException(400, "already submitted, cannot modify")

    for ann_data in data.annotations:
        existing = db.query(Annotation).filter(
            Annotation.assignment_id == assignment.id,
            Annotation.checkpoint_id == ann_data.checkpoint_id,
        ).first()

        if existing:
            existing.score = ann_data.score
            existing.fail_code = ann_data.fail_code
            existing.evidence_ts = ann_data.evidence_ts
            existing.note = ann_data.note
            existing.submitted_at = datetime.utcnow()
        else:
            ann = Annotation(
                assignment_id=assignment.id,
                checkpoint_id=ann_data.checkpoint_id,
                score=ann_data.score,
                fail_code=ann_data.fail_code,
                evidence_ts=ann_data.evidence_ts,
                note=ann_data.note,
            )
            db.add(ann)

    db.commit()
    return {"status": "saved", "count": len(data.annotations)}


@router.post("/submit-and-lock")
def submit_and_lock(data: BatchAnnotationSubmit, db: Session = Depends(get_db)):
    assignment = db.query(Assignment).filter(Assignment.id == data.assignment_id).first()
    if not assignment:
        raise HTTPException(404, "assignment not found")
    if assignment.status == "submitted":
        raise HTTPException(400, "already submitted")

    for ann_data in data.annotations:
        existing = db.query(Annotation).filter(
            Annotation.assignment_id == assignment.id,
            Annotation.checkpoint_id == ann_data.checkpoint_id,
        ).first()

        if existing:
            existing.score = ann_data.score
            existing.fail_code = ann_data.fail_code
            existing.evidence_ts = ann_data.evidence_ts
            existing.note = ann_data.note
            existing.submitted_at = datetime.utcnow()
        else:
            ann = Annotation(
                assignment_id=assignment.id,
                checkpoint_id=ann_data.checkpoint_id,
                score=ann_data.score,
                fail_code=ann_data.fail_code,
                evidence_ts=ann_data.evidence_ts,
                note=ann_data.note,
            )
            db.add(ann)

    assignment.status = "submitted"
    assignment.submitted_at = datetime.utcnow()
    db.commit()

    result = {"status": "locked", "count": len(data.annotations)}

    if assignment.role in ("A", "B"):
        other_role = "B" if assignment.role == "A" else "A"
        other = db.query(Assignment).filter(
            Assignment.video_id == assignment.video_id,
            Assignment.role == other_role,
            Assignment.status == "submitted",
        ).first()
        if other:
            compare_result = compare_and_adjudicate(db, assignment.video_id)
            result["comparison"] = compare_result

    if assignment.role == "third":
        from app.services.comparator import resolve_with_third
        resolve_result = resolve_with_third(db, assignment.video_id)
        result["resolution"] = resolve_result

    return result


@router.get("/assignment/{assignment_id}")
def get_annotations(assignment_id: int, db: Session = Depends(get_db)):
    anns = db.query(Annotation).filter(Annotation.assignment_id == assignment_id).all()
    return [
        {
            "id": a.id,
            "checkpoint_id": a.checkpoint_id,
            "score": a.score,
            "fail_code": a.fail_code,
            "evidence_ts": a.evidence_ts,
            "note": a.note,
        }
        for a in anns
    ]
