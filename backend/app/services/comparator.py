from sqlalchemy.orm import Session
from app.models import Assignment, Annotation, FinalResult, Checkpoint, Video
import random


def compare_and_adjudicate(db: Session, video_id: int) -> dict:
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        return {"error": "video not found"}

    assignments_a = db.query(Assignment).filter(
        Assignment.video_id == video_id,
        Assignment.role == "A",
        Assignment.status == "submitted",
    ).first()
    assignments_b = db.query(Assignment).filter(
        Assignment.video_id == video_id,
        Assignment.role == "B",
        Assignment.status == "submitted",
    ).first()

    if not assignments_a or not assignments_b:
        return {"error": "A and B not both submitted"}

    checkpoints = db.query(Checkpoint).filter(
        Checkpoint.question_id == video.question_id
    ).all()

    stats = {"consensus": 0, "need_third": 0, "total": len(checkpoints)}

    for cp in checkpoints:
        existing = db.query(FinalResult).filter(
            FinalResult.video_id == video_id,
            FinalResult.checkpoint_id == cp.id,
        ).first()
        if existing:
            continue

        ann_a = db.query(Annotation).filter(
            Annotation.assignment_id == assignments_a.id,
            Annotation.checkpoint_id == cp.id,
        ).first()
        ann_b = db.query(Annotation).filter(
            Annotation.assignment_id == assignments_b.id,
            Annotation.checkpoint_id == cp.id,
        ).first()

        if not ann_a or not ann_b:
            continue

        if ann_a.score == ann_b.score:
            final = FinalResult(
                video_id=video_id,
                checkpoint_id=cp.id,
                final_score=ann_a.score,
                final_fail_code=ann_a.fail_code or ann_b.fail_code,
                method="consensus",
            )
            db.add(final)
            stats["consensus"] += 1
        else:
            stats["need_third"] += 1

    db.commit()
    return stats


def resolve_with_third(db: Session, video_id: int) -> dict:
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        return {"error": "video not found"}

    third_assignment = db.query(Assignment).filter(
        Assignment.video_id == video_id,
        Assignment.role == "third",
        Assignment.status == "submitted",
    ).first()

    if not third_assignment:
        return {"error": "third not submitted"}

    assignments_a = db.query(Assignment).filter(
        Assignment.video_id == video_id, Assignment.role == "A"
    ).first()
    assignments_b = db.query(Assignment).filter(
        Assignment.video_id == video_id, Assignment.role == "B"
    ).first()

    checkpoints = db.query(Checkpoint).filter(
        Checkpoint.question_id == video.question_id
    ).all()

    stats = {"majority": 0, "need_expert": 0}

    for cp in checkpoints:
        existing = db.query(FinalResult).filter(
            FinalResult.video_id == video_id,
            FinalResult.checkpoint_id == cp.id,
        ).first()
        if existing:
            continue

        ann_a = db.query(Annotation).filter(
            Annotation.assignment_id == assignments_a.id,
            Annotation.checkpoint_id == cp.id,
        ).first()
        ann_b = db.query(Annotation).filter(
            Annotation.assignment_id == assignments_b.id,
            Annotation.checkpoint_id == cp.id,
        ).first()
        ann_third = db.query(Annotation).filter(
            Annotation.assignment_id == third_assignment.id,
            Annotation.checkpoint_id == cp.id,
        ).first()

        if not ann_third:
            continue

        scores = [ann_a.score if ann_a else None, ann_b.score if ann_b else None, ann_third.score]
        scores = [s for s in scores if s]

        from collections import Counter
        counts = Counter(scores)
        majority_score, majority_count = counts.most_common(1)[0]

        if majority_count >= 2:
            matching_anns = []
            if ann_a and ann_a.score == majority_score:
                matching_anns.append(ann_a)
            if ann_b and ann_b.score == majority_score:
                matching_anns.append(ann_b)
            if ann_third.score == majority_score:
                matching_anns.append(ann_third)

            fail_code = next((a.fail_code for a in matching_anns if a.fail_code), None)

            final = FinalResult(
                video_id=video_id,
                checkpoint_id=cp.id,
                final_score=majority_score,
                final_fail_code=fail_code,
                method="majority",
            )
            db.add(final)
            stats["majority"] += 1
        else:
            # All three disagree: assign to admin (expert) for final decision
            final = FinalResult(
                video_id=video_id,
                checkpoint_id=cp.id,
                final_score="",
                method="pending_expert",
            )
            db.add(final)
            stats["need_expert"] += 1

    # If any need expert, auto-assign expert role to admin (user_id=1)
    if stats["need_expert"] > 0:
        existing_expert = db.query(Assignment).filter(
            Assignment.video_id == video_id,
            Assignment.role == "expert",
        ).first()
        if not existing_expert:
            db.add(Assignment(
                video_id=video_id,
                annotator_id=1,  # 陈逸菲 (admin)
                role="expert",
            ))

    db.commit()
    return stats


def get_disagreed_checkpoints(db: Session, video_id: int) -> list[int]:
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        return []

    assignments_a = db.query(Assignment).filter(
        Assignment.video_id == video_id, Assignment.role == "A", Assignment.status == "submitted"
    ).first()
    assignments_b = db.query(Assignment).filter(
        Assignment.video_id == video_id, Assignment.role == "B", Assignment.status == "submitted"
    ).first()

    if not assignments_a or not assignments_b:
        return []

    checkpoints = db.query(Checkpoint).filter(
        Checkpoint.question_id == video.question_id
    ).all()

    disagreed = []
    for cp in checkpoints:
        ann_a = db.query(Annotation).filter(
            Annotation.assignment_id == assignments_a.id, Annotation.checkpoint_id == cp.id
        ).first()
        ann_b = db.query(Annotation).filter(
            Annotation.assignment_id == assignments_b.id, Annotation.checkpoint_id == cp.id
        ).first()
        if ann_a and ann_b and ann_a.score != ann_b.score:
            disagreed.append(cp.id)

    return disagreed
