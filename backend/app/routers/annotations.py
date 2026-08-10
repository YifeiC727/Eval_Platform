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


@router.post("/complete")
def complete_assignment(data: dict, db: Session = Depends(get_db)):
    """标记单题为已完成（不锁定，可修改）"""
    assignment_id = data.get("assignment_id")
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(404, "assignment not found")
    if assignment.status != "submitted":
        assignment.status = "completed"
        db.commit()
    return {"status": "completed"}


@router.post("/submit-all")
def submit_all(data: dict, db: Session = Depends(get_db)):
    """全部提交锁定：要求所有任务要么已完成要么技术无效"""
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id required")

    assignments = db.query(Assignment).filter(Assignment.annotator_id == user_id).all()

    incomplete = []
    for a in assignments:
        if a.status not in ("completed", "submitted", "issue_reported", "invalidated"):
            video = a.video
            question = video.question if video else None
            incomplete.append(question.question_id if question else f"V{a.video_id}")

    if incomplete:
        raise HTTPException(400, f"还有 {len(incomplete)} 题未完成: {', '.join(incomplete[:5])}{'...' if len(incomplete) > 5 else ''}")

    locked = 0
    for a in assignments:
        if a.status == "completed":
            a.status = "submitted"
            a.submitted_at = datetime.utcnow()
            locked += 1

            # Trigger finalization logic
            other = db.query(Assignment).filter(
                Assignment.video_id == a.video_id,
                Assignment.role != a.role,
                Assignment.role.in_(["A", "B"]),
            ).first()

            if other and other.status == "submitted":
                from app.services.comparator import compare_and_adjudicate
                compare_and_adjudicate(db, a.video_id)
            elif not other:
                # Single mode: directly finalize
                from app.models import FinalResult
                anns = db.query(Annotation).filter(Annotation.assignment_id == a.id).all()
                for ann in anns:
                    existing = db.query(FinalResult).filter(
                        FinalResult.video_id == a.video_id,
                        FinalResult.checkpoint_id == ann.checkpoint_id,
                    ).first()
                    if not existing:
                        db.add(FinalResult(
                            video_id=a.video_id,
                            checkpoint_id=ann.checkpoint_id,
                            final_score=ann.score,
                            final_fail_code=ann.fail_code,
                            method="single",
                        ))

    db.commit()
    return {"status": "locked", "locked_count": locked}
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
        ).first()

        if other and other.status == "submitted":
            # Dual mode: both submitted, run comparison
            compare_result = compare_and_adjudicate(db, assignment.video_id)
            result["comparison"] = compare_result
        elif not other:
            # Single mode: no B assigned, directly finalize
            from app.models import FinalResult
            annotations_list = db.query(Annotation).filter(
                Annotation.assignment_id == assignment.id
            ).all()
            finalized = 0
            for ann in annotations_list:
                existing_final = db.query(FinalResult).filter(
                    FinalResult.video_id == assignment.video_id,
                    FinalResult.checkpoint_id == ann.checkpoint_id,
                ).first()
                if not existing_final:
                    fr = FinalResult(
                        video_id=assignment.video_id,
                        checkpoint_id=ann.checkpoint_id,
                        final_score=ann.score,
                        final_fail_code=ann.fail_code,
                        method="single",
                    )
                    db.add(fr)
                    finalized += 1
            db.commit()
            result["finalized"] = finalized

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
