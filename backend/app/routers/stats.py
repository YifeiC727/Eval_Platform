from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Project, Question, Video, Checkpoint, Assignment, Annotation, FinalResult, User

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def get_overview(project_id: int = None, db: Session = Depends(get_db)):
    q_query = db.query(func.count(Question.id))
    v_query = db.query(func.count(Video.id))
    cp_query = db.query(func.count(Checkpoint.id))

    if project_id:
        q_query = q_query.filter(Question.project_id == project_id)
        v_query = v_query.join(Question).filter(Question.project_id == project_id)
        cp_query = cp_query.join(Question).filter(Question.project_id == project_id)

    total_questions = q_query.scalar()
    total_videos = v_query.scalar()
    total_checkpoints = cp_query.scalar()

    assigned_videos = db.query(func.count(func.distinct(Assignment.video_id)))
    if project_id:
        assigned_videos = assigned_videos.join(Video).join(Question).filter(Question.project_id == project_id)
    assigned_videos = assigned_videos.scalar()

    submitted_assignments = db.query(func.count(Assignment.id)).filter(Assignment.status == "submitted")
    if project_id:
        submitted_assignments = submitted_assignments.join(Video).join(Question).filter(Question.project_id == project_id)
    submitted_count = submitted_assignments.scalar()

    finalized_query = db.query(func.count(FinalResult.id)).filter(
        FinalResult.method.in_(["consensus", "majority", "expert", "single"])
    )
    pending_third_query = db.query(func.count(FinalResult.id)).filter(FinalResult.method == "pending_third")
    pending_expert_query = db.query(func.count(FinalResult.id)).filter(FinalResult.method == "pending_expert")

    if project_id:
        finalized_query = finalized_query.join(Checkpoint, FinalResult.checkpoint_id == Checkpoint.id).join(Question).filter(Question.project_id == project_id)
        pending_third_query = pending_third_query.join(Checkpoint, FinalResult.checkpoint_id == Checkpoint.id).join(Question).filter(Question.project_id == project_id)
        pending_expert_query = pending_expert_query.join(Checkpoint, FinalResult.checkpoint_id == Checkpoint.id).join(Question).filter(Question.project_id == project_id)

    finalized = finalized_query.scalar()
    pending_third = pending_third_query.scalar()
    pending_expert = pending_expert_query.scalar()

    # Video-level progress
    videos_both_submitted = 0
    videos_one_submitted = 0
    both_submitted_video_ids = []
    if total_videos > 0:
        video_status = db.query(
            Assignment.video_id,
            func.count(Assignment.id).filter(Assignment.status == "submitted").label("submitted_count"),
        ).filter(Assignment.role.in_(["A", "B"])).group_by(Assignment.video_id).all()

        for vid, count in video_status:
            if count >= 2:
                videos_both_submitted += 1
                both_submitted_video_ids.append(vid)
            elif count == 1:
                videos_one_submitted += 1

    # "待比对" = checkpoints in videos where both A/B submitted, minus already finalized/pending
    ready_for_compare = 0
    if both_submitted_video_ids:
        for vid in both_submitted_video_ids:
            video = db.query(Video).filter(Video.id == vid).first()
            if video:
                cp_count = db.query(func.count(Checkpoint.id)).filter(
                    Checkpoint.question_id == video.question_id
                ).scalar()
                already_handled = db.query(func.count(FinalResult.id)).filter(
                    FinalResult.video_id == vid
                ).scalar()
                ready_for_compare += (cp_count - already_handled)

    return {
        "total_questions": total_questions,
        "total_videos": total_videos,
        "total_checkpoints": total_checkpoints,
        "assigned_videos": assigned_videos,
        "unassigned_videos": total_videos - assigned_videos,
        "annotation_progress": {
            "not_started": total_videos - assigned_videos,
            "in_progress": assigned_videos - videos_both_submitted,
            "both_submitted": videos_both_submitted,
        },
        "adjudication": {
            "finalized": finalized,
            "pending_third": pending_third,
            "pending_expert": pending_expert,
            "ready_for_compare": ready_for_compare,
        },
        "submitted_annotations": submitted_count,
    }


@router.get("/annotators")
def get_annotator_stats(project_id: int = None, db: Session = Depends(get_db)):
    annotators = db.query(User).filter(User.role == "annotator").all()

    result = []
    for user in annotators:
        assignments = db.query(Assignment).filter(Assignment.annotator_id == user.id)
        if project_id:
            assignments = assignments.join(Video).join(Question).filter(Question.project_id == project_id)
        all_assignments = assignments.all()

        total_tasks = len(all_assignments)
        submitted_tasks = sum(1 for a in all_assignments if a.status == "submitted")
        pending_tasks = total_tasks - submitted_tasks

        total_annotations = 0
        for a in all_assignments:
            total_annotations += db.query(func.count(Annotation.id)).filter(
                Annotation.assignment_id == a.id
            ).scalar()

        result.append({
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "password": user.password_plain or "",
            "total_tasks": total_tasks,
            "submitted_tasks": submitted_tasks,
            "pending_tasks": pending_tasks,
            "total_annotations": total_annotations,
            "completion_rate": round(submitted_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0,
        })

    result.sort(key=lambda x: x["submitted_tasks"], reverse=True)
    return result


@router.get("/recent-activity")
def get_recent_activity(limit: int = 20, db: Session = Depends(get_db)):
    recent_submissions = db.query(Assignment).filter(
        Assignment.status == "submitted"
    ).order_by(Assignment.submitted_at.desc()).limit(limit).all()

    activities = []
    for a in recent_submissions:
        video = a.video
        question = video.question if video else None
        annotator = a.annotator
        activities.append({
            "type": "submission",
            "time": a.submitted_at.isoformat() if a.submitted_at else None,
            "annotator": annotator.display_name if annotator else "",
            "role": a.role,
            "video_id": video.video_id if video else "",
            "question_id": question.question_id if question else "",
            "prompt_summary": (question.prompt[:50] + "...") if question and len(question.prompt) > 50 else (question.prompt if question else ""),
        })

    return activities
