from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EvalBatch, QuestionBank, Question, Checkpoint, Video, Assignment, Annotation, FinalResult, User

router = APIRouter(prefix="/api/batches", tags=["eval-batches"])


@router.get("/")
def list_batches(db: Session = Depends(get_db)):
    batches = db.query(EvalBatch).order_by(EvalBatch.created_at.desc()).all()
    result = []
    for b in batches:
        total_videos = db.query(func.count(Video.id)).filter(Video.batch_id == b.id).scalar()
        assigned = db.query(func.count(func.distinct(Assignment.video_id))).join(Video).filter(Video.batch_id == b.id).scalar()
        submitted = db.query(func.count(Assignment.id)).join(Video).filter(
            Video.batch_id == b.id, Assignment.status == "submitted"
        ).scalar()
        finalized = db.query(func.count(FinalResult.id)).join(Video).filter(Video.batch_id == b.id).scalar()
        total_cps = db.query(func.count(Checkpoint.id)).join(Question).filter(Question.bank_id == b.bank_id).scalar()

        progress = 0
        if total_videos > 0 and assigned > 0:
            progress = round(submitted / (assigned if b.annotation_mode == "single" else assigned) * 100)

        result.append({
            "id": b.id,
            "name": b.name,
            "bank_id": b.bank_id,
            "bank_name": b.bank.name if b.bank else "",
            "model_version": b.model_version,
            "annotation_mode": b.annotation_mode,
            "status": b.status,
            "description": b.description or "",
            "total_videos": total_videos,
            "assigned_videos": assigned,
            "submitted_assignments": submitted,
            "finalized_checkpoints": finalized,
            "total_checkpoints": total_cps,
            "progress": progress,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return result


@router.post("/")
def create_batch(data: dict, db: Session = Depends(get_db)):
    bank_id = data.get("bank_id")
    if not bank_id:
        raise HTTPException(400, "bank_id required")
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank:
        raise HTTPException(404, "question bank not found")

    batch = EvalBatch(
        name=data.get("name", f"{bank.name} - {data.get('model_version', '')}"),
        bank_id=bank_id,
        model_version=data.get("model_version", ""),
        annotation_mode=data.get("annotation_mode", "single"),
        description=data.get("description", ""),
    )
    db.add(batch)
    db.flush()

    # Create video records from bank questions
    questions = db.query(Question).filter(Question.bank_id == bank_id).all()
    video_urls = data.get("video_urls", {})  # {question_id: url}

    for q in questions:
        seq = q.question_id.replace("Q", "")
        v = Video(
            video_id=f"V{seq}",
            batch_id=batch.id,
            question_id=q.id,
            oss_url=video_urls.get(q.question_id, ""),
        )
        db.add(v)

    db.commit()
    db.refresh(batch)
    return {
        "id": batch.id,
        "name": batch.name,
        "videos_created": len(questions),
    }


@router.get("/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    total_videos = db.query(func.count(Video.id)).filter(Video.batch_id == batch_id).scalar()
    assigned = db.query(func.count(func.distinct(Assignment.video_id))).join(Video).filter(Video.batch_id == batch_id).scalar()
    submitted = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.status == "submitted"
    ).scalar()
    finalized = db.query(func.count(FinalResult.id)).join(Video).filter(Video.batch_id == batch_id).scalar()

    return {
        "id": batch.id,
        "name": batch.name,
        "bank_id": batch.bank_id,
        "bank_name": batch.bank.name if batch.bank else "",
        "model_version": batch.model_version,
        "annotation_mode": batch.annotation_mode,
        "status": batch.status,
        "description": batch.description,
        "total_videos": total_videos,
        "assigned_videos": assigned,
        "submitted_assignments": submitted,
        "finalized_checkpoints": finalized,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


@router.delete("/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    video_ids = [v.id for v in videos]
    if video_ids:
        assignment_ids = [a.id for a in db.query(Assignment).filter(Assignment.video_id.in_(video_ids)).all()]
        if assignment_ids:
            db.query(Annotation).filter(Annotation.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)
        db.query(Assignment).filter(Assignment.video_id.in_(video_ids)).delete(synchronize_session=False)
        db.query(FinalResult).filter(FinalResult.video_id.in_(video_ids)).delete(synchronize_session=False)
        db.query(Video).filter(Video.batch_id == batch_id).delete(synchronize_session=False)

    db.delete(batch)
    db.commit()
    return {"status": "deleted"}


@router.post("/{batch_id}/update-urls")
def update_video_urls(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """批量更新视频URL: {"urls": {"Q0001": "http://...", "Q0002": "http://..."}}"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    urls = data.get("urls", {})
    updated = 0
    for q_id, url in urls.items():
        video = db.query(Video).join(Question).filter(
            Video.batch_id == batch_id, Question.question_id == q_id
        ).first()
        if video:
            video.oss_url = url
            updated += 1

    db.commit()
    return {"updated": updated}


@router.post("/{batch_id}/assign")
def assign_batch(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """为批次分配标注员"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    annotator_ids = data.get("annotator_ids", [])
    if not annotator_ids:
        raise HTTPException(400, "annotator_ids required")

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]

    n = len(annotator_ids)
    created = 0

    if batch.annotation_mode == "single":
        if n < 1:
            raise HTTPException(400, "need at least 1 annotator")
        for idx, video in enumerate(unassigned):
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[idx % n], role="A"))
            created += 1
    else:
        if n < 2:
            raise HTTPException(400, "dual mode needs at least 2 annotators")
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            b_idx = (idx + 1) % n
            if b_idx == a_idx:
                b_idx = (idx + 2) % n
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[a_idx], role="A"))
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[b_idx], role="B"))
            created += 2

    if batch.status == "preparing":
        batch.status = "labeling"
    db.commit()

    per_person = {}
    for aid in annotator_ids:
        user = db.query(User).filter(User.id == aid).first()
        count = db.query(Assignment).join(Video).filter(Video.batch_id == batch_id, Assignment.annotator_id == aid).count()
        per_person[user.display_name or user.username] = count

    return {"created": created, "videos_assigned": len(unassigned), "per_person": per_person}


@router.get("/{batch_id}/scores")
def batch_scores(batch_id: int, db: Session = Depends(get_db)):
    """获取某批次的能力得分"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    SCORE_MAP = {"C": 1.0, "R": 0.3, "N": 0.0}

    results = db.query(Checkpoint, FinalResult).join(
        FinalResult, FinalResult.checkpoint_id == Checkpoint.id
    ).join(Video, FinalResult.video_id == Video.id).filter(
        Video.batch_id == batch_id,
        FinalResult.final_score.in_(["C", "R", "N"]),
    ).all()

    from collections import defaultdict
    ability_data = defaultdict(lambda: {"name": "", "scores": [], "c": 0, "r": 0, "n": 0})
    for cp, fr in results:
        aid = cp.ability_id or "UNKNOWN"
        ability_data[aid]["name"] = cp.ability_name or ""
        ability_data[aid]["scores"].append(SCORE_MAP.get(fr.final_score, 0))
        if fr.final_score == "C": ability_data[aid]["c"] += 1
        elif fr.final_score == "R": ability_data[aid]["r"] += 1
        else: ability_data[aid]["n"] += 1

    scores = []
    for aid in sorted(ability_data.keys()):
        d = ability_data[aid]
        n = len(d["scores"])
        score = round(sum(d["scores"]) / n * 100, 1) if n > 0 else 0
        scores.append({
            "ability_id": aid,
            "ability_name": d["name"],
            "score": score,
            "c_count": d["c"], "r_count": d["r"], "n_count": d["n"],
            "total_n": n,
        })

    scores.sort(key=lambda x: x["score"])
    return scores


@router.get("/compare")
def compare_batches(batch_a: int, batch_b: int, db: Session = Depends(get_db)):
    """对比两个批次的能力得分"""
    scores_a = {s["ability_id"]: s for s in batch_scores(batch_a, db)}
    scores_b = {s["ability_id"]: s for s in batch_scores(batch_b, db)}

    all_abilities = sorted(set(list(scores_a.keys()) + list(scores_b.keys())))

    ba = db.query(EvalBatch).filter(EvalBatch.id == batch_a).first()
    bb = db.query(EvalBatch).filter(EvalBatch.id == batch_b).first()

    comparison = []
    for aid in all_abilities:
        a = scores_a.get(aid, {})
        b = scores_b.get(aid, {})
        sa = a.get("score", 0)
        sb = b.get("score", 0)
        comparison.append({
            "ability_id": aid,
            "ability_name": a.get("ability_name") or b.get("ability_name", ""),
            "score_a": sa,
            "score_b": sb,
            "delta": round(sb - sa, 1),
            "n_a": a.get("total_n", 0),
            "n_b": b.get("total_n", 0),
        })

    comparison.sort(key=lambda x: x["delta"])
    return {
        "batch_a": {"id": batch_a, "name": ba.name if ba else "", "model": ba.model_version if ba else ""},
        "batch_b": {"id": batch_b, "name": bb.name if bb else "", "model": bb.model_version if bb else ""},
        "comparison": comparison,
    }
