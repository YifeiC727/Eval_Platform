from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import Question, Checkpoint, Video, Assignment, Annotation, User, FinalResult
import random

router = APIRouter(prefix="/api/qc", tags=["quality-control"])


@router.get("/search")
def search_questions(
    q: str = "",
    project_id: int = None,
    ability_id: str = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """搜索题目：支持 Prompt 关键词、题目ID、能力ID 筛选"""
    query = db.query(Question)
    if project_id:
        query = query.filter(Question.project_id == project_id)
    if q:
        query = query.filter(
            or_(
                Question.prompt.contains(q),
                Question.question_id.contains(q),
            )
        )
    if ability_id:
        cp_question_ids = db.query(Checkpoint.question_id).filter(
            Checkpoint.ability_id == ability_id
        ).distinct().all()
        cp_qids = [r[0] for r in cp_question_ids]
        query = query.filter(Question.id.in_(cp_qids))

    total = query.count()
    questions = query.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for question in questions:
        video = db.query(Video).filter(Video.question_id == question.id).first()
        result.append({
            "id": question.id,
            "question_id": question.question_id,
            "prompt": question.prompt,
            "language": question.language,
            "checkpoint_count": len(question.checkpoints),
            "video_id": video.video_id if video else None,
            "abilities": list(set(cp.ability_id for cp in question.checkpoints if cp.ability_id)),
        })

    return {"total": total, "page": page, "page_size": page_size, "items": result}


@router.get("/compare/{video_id}")
def compare_ab_annotations(video_id: str, db: Session = Depends(get_db)):
    """A/B 对比视图：并排显示两人判定"""
    video = db.query(Video).filter(Video.video_id == video_id).first()
    if not video:
        raise HTTPException(404, "video not found")

    question = video.question
    checkpoints = db.query(Checkpoint).filter(
        Checkpoint.question_id == question.id
    ).order_by(Checkpoint.seq).all()

    a_assign = db.query(Assignment).filter(
        Assignment.video_id == video.id, Assignment.role == "A"
    ).first()
    b_assign = db.query(Assignment).filter(
        Assignment.video_id == video.id, Assignment.role == "B"
    ).first()
    third_assign = db.query(Assignment).filter(
        Assignment.video_id == video.id, Assignment.role == "third"
    ).first()

    a_anns = {}
    b_anns = {}
    third_anns = {}
    if a_assign:
        for ann in db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).all():
            a_anns[ann.checkpoint_id] = ann
    if b_assign:
        for ann in db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).all():
            b_anns[ann.checkpoint_id] = ann
    if third_assign:
        for ann in db.query(Annotation).filter(Annotation.assignment_id == third_assign.id).all():
            third_anns[ann.checkpoint_id] = ann

    final_map = {}
    for fr in db.query(FinalResult).filter(FinalResult.video_id == video.id).all():
        final_map[fr.checkpoint_id] = fr

    comparison = []
    agree_count = 0
    disagree_count = 0

    for cp in checkpoints:
        a = a_anns.get(cp.id)
        b = b_anns.get(cp.id)
        t = third_anns.get(cp.id)
        f = final_map.get(cp.id)

        is_agree = a and b and a.score == b.score

        if a and b:
            if is_agree:
                agree_count += 1
            else:
                disagree_count += 1

        comparison.append({
            "checkpoint_id": cp.checkpoint_id,
            "seq": cp.seq,
            "text": cp.text,
            "min_success_line": cp.min_success_line,
            "ability_id": cp.ability_id,
            "a_score": a.score if a else None,
            "a_fail_code": a.fail_code if a else None,
            "a_note": a.note if a else None,
            "b_score": b.score if b else None,
            "b_fail_code": b.fail_code if b else None,
            "b_note": b.note if b else None,
            "third_score": t.score if t else None,
            "third_fail_code": t.fail_code if t else None,
            "final_score": f.final_score if f else None,
            "final_method": f.method if f else None,
            "is_agree": is_agree,
        })

    return {
        "video_id": video.video_id,
        "question_id": question.question_id,
        "prompt": question.prompt,
        "oss_url": video.oss_url,
        "annotator_a": a_assign.annotator.display_name if a_assign and a_assign.annotator else None,
        "annotator_b": b_assign.annotator.display_name if b_assign and b_assign.annotator else None,
        "annotator_third": third_assign.annotator.display_name if third_assign and third_assign.annotator else None,
        "agree_count": agree_count,
        "disagree_count": disagree_count,
        "total_checkpoints": len(checkpoints),
        "comparison": comparison,
    }


@router.get("/sample")
def sample_for_review(project_id: int = None, count: int = 10, db: Session = Depends(get_db)):
    """随机抽取已完成的视频供质检"""
    query = db.query(Video).join(Assignment).filter(Assignment.status == "submitted")
    if project_id:
        query = query.join(Question).filter(Question.project_id == project_id)

    videos = query.distinct().all()
    if not videos:
        return {"items": [], "total_pool": 0}

    sample_count = min(count, len(videos))
    sampled = random.sample(videos, sample_count)

    result = []
    for video in sampled:
        question = video.question
        a_assign = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.role == "A", Assignment.status == "submitted"
        ).first()
        b_assign = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.role == "B", Assignment.status == "submitted"
        ).first()

        result.append({
            "video_id": video.video_id,
            "question_id": question.question_id if question else "",
            "prompt_summary": (question.prompt[:80] + "...") if question and len(question.prompt) > 80 else (question.prompt if question else ""),
            "annotator_a": a_assign.annotator.display_name if a_assign and a_assign.annotator else None,
            "annotator_b": b_assign.annotator.display_name if b_assign and b_assign.annotator else None,
            "checkpoint_count": len(question.checkpoints) if question else 0,
        })

    return {"items": result, "total_pool": len(videos), "sampled": sample_count}
