import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Assignment, Video, Question, Checkpoint, User, FinalResult, Annotation
from app.schemas import AssignmentOut, AssignmentCreate

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


@router.post("/clear")
def clear_assignments(data: dict = {}, db: Session = Depends(get_db)):
    """清除所有已分配任务、标注和定案"""
    project_id = data.get("project_id")

    if project_id:
        video_ids = [v.id for v in db.query(Video).join(Question).filter(Question.project_id == project_id).all()]
        finals = db.query(FinalResult).filter(FinalResult.video_id.in_(video_ids)).delete(synchronize_session=False)
        assignment_ids = [a.id for a in db.query(Assignment).filter(Assignment.video_id.in_(video_ids)).all()]
        anns = db.query(Annotation).filter(Annotation.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)
        assignments = db.query(Assignment).filter(Assignment.video_id.in_(video_ids)).delete(synchronize_session=False)
    else:
        finals = db.query(FinalResult).delete(synchronize_session=False)
        anns = db.query(Annotation).delete(synchronize_session=False)
        assignments = db.query(Assignment).delete(synchronize_session=False)

    db.commit()
    return {
        "deleted_assignments": assignments,
        "deleted_annotations": anns,
        "deleted_finals": finals,
    }


@router.post("/", response_model=AssignmentOut)
def create_assignment(data: AssignmentCreate, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == data.video_id).first()
    if not video:
        raise HTTPException(404, "video not found")
    user = db.query(User).filter(User.id == data.annotator_id).first()
    if not user:
        raise HTTPException(404, "user not found")
    if data.role not in ("A", "B", "third", "expert"):
        raise HTTPException(400, "role must be A, B, third, or expert")

    existing = db.query(Assignment).filter(
        Assignment.video_id == data.video_id,
        Assignment.role == data.role,
    ).first()
    if existing:
        raise HTTPException(400, f"role {data.role} already assigned for this video")

    a = Assignment(
        video_id=data.video_id,
        annotator_id=data.annotator_id,
        role=data.role,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.post("/batch")
def batch_assign(data: dict, db: Session = Depends(get_db)):
    """旧接口保留兼容，内部走均匀轮转"""
    data["mode"] = "round_robin"
    return assign_by_mode(data, db)


@router.post("/assign")
def assign_by_mode(data: dict, db: Session = Depends(get_db)):
    mode = data.get("mode", "round_robin")
    project_id = data.get("project_id")
    annotator_ids = data.get("annotator_ids", [])
    annotation_mode = data.get("annotation_mode", "dual")

    if not project_id:
        raise HTTPException(400, "project_id required")

    if mode == "round_robin":
        return _assign_round_robin(db, project_id, annotator_ids, annotation_mode)
    elif mode == "manual":
        assignments_list = data.get("assignments", [])
        return _assign_manual(db, assignments_list)
    elif mode == "preview":
        return _assign_preview(db, project_id, annotator_ids, annotation_mode)
    else:
        raise HTTPException(400, "mode must be round_robin, manual, or preview")


def _assign_round_robin(db: Session, project_id: int, annotator_ids: list, annotation_mode: str = "dual") -> dict:
    min_annotators = 2 if annotation_mode == "dual" else 1
    if len(annotator_ids) < min_annotators:
        raise HTTPException(400, f"need at least {min_annotators} annotators")

    videos = db.query(Video).join(Question).filter(Question.project_id == project_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]

    n = len(annotator_ids)
    created = 0

    if annotation_mode == "single":
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[a_idx], role="A"))
            created += 1
    else:
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            b_idx = (idx + 1) % n
            if b_idx == a_idx:
                b_idx = (idx + 2) % n
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[a_idx], role="A"))
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[b_idx], role="B"))
            created += 2

    db.commit()

    per_person = {}
    for aid in annotator_ids:
        count = db.query(Assignment).filter(Assignment.annotator_id == aid).count()
        user = db.query(User).filter(User.id == aid).first()
        per_person[user.display_name or user.username] = count

    return {"created": created, "videos_assigned": len(unassigned), "total_videos": len(videos), "per_person": per_person}


def _assign_manual(db: Session, assignments_list: list) -> dict:
    """手动指派: [{video_id, annotator_a_id, annotator_b_id}, ...]"""
    created = 0
    skipped = 0
    for item in assignments_list:
        video_id = item.get("video_id")
        a_id = item.get("annotator_a_id")
        b_id = item.get("annotator_b_id")

        if not video_id or not a_id or not b_id:
            skipped += 1
            continue

        existing = db.query(Assignment).filter(Assignment.video_id == video_id).count()
        if existing > 0:
            skipped += 1
            continue

        db.add(Assignment(video_id=video_id, annotator_id=a_id, role="A"))
        db.add(Assignment(video_id=video_id, annotator_id=b_id, role="B"))
        created += 2

    db.commit()
    return {"created": created, "skipped": skipped}


def _assign_preview(db: Session, project_id: int, annotator_ids: list, annotation_mode: str = "dual") -> dict:
    """预览均匀轮转结果，不写入数据库"""
    min_annotators = 2 if annotation_mode == "dual" else 1
    if len(annotator_ids) < min_annotators:
        raise HTTPException(400, f"need at least {min_annotators} annotators")

    videos = db.query(Video).join(Question).filter(Question.project_id == project_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]

    n = len(annotator_ids)
    user_map = {}
    for aid in annotator_ids:
        user = db.query(User).filter(User.id == aid).first()
        user_map[aid] = user.display_name or user.username if user else str(aid)

    preview = []
    per_person = {aid: 0 for aid in annotator_ids}

    if annotation_mode == "single":
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            a_id = annotator_ids[a_idx]
            per_person[a_id] += 1
            question = video.question
            preview.append({
                "video_id": video.video_id,
                "video_id_str": video.video_id,
                "question_id": question.question_id if question else "",
                "prompt_summary": (question.prompt[:60] + "...") if question and len(question.prompt) > 60 else (question.prompt if question else ""),
                "annotator_a": user_map[a_id],
                "annotator_a_name": user_map[a_id],
                "annotator_b": "-",
                "annotator_b_name": "-",
            })
    else:
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            b_idx = (idx + 1) % n
            if b_idx == a_idx:
                b_idx = (idx + 2) % n
            a_id = annotator_ids[a_idx]
            b_id = annotator_ids[b_idx]
            per_person[a_id] += 1
            per_person[b_id] += 1
            question = video.question
            preview.append({
                "video_id": video.video_id,
                "video_id_str": video.video_id,
                "question_id": question.question_id if question else "",
                "prompt_summary": (question.prompt[:60] + "...") if question and len(question.prompt) > 60 else (question.prompt if question else ""),
                "annotator_a": user_map[a_id],
                "annotator_a_name": user_map[a_id],
                "annotator_b": user_map[b_id],
                "annotator_b_name": user_map[b_id],
            })

    per_person_named = {user_map[k]: v for k, v in per_person.items()}
    return {
        "mode": "round_robin",
        "annotation_mode": annotation_mode,
        "total_to_assign": len(unassigned),
        "per_person": per_person_named,
        "preview": preview[:20],
        "plan_count": len(preview),
    }


@router.post("/ai-suggest")
def ai_suggest_assignment(data: dict, db: Session = Depends(get_db)):
    """根据用户自然语言描述生成分配方案预览"""
    project_id = data.get("project_id")
    annotator_ids = data.get("annotator_ids", [])
    instruction = data.get("instruction", "")
    annotation_mode = data.get("annotation_mode", "dual")

    if not project_id or not annotator_ids:
        raise HTTPException(400, "project_id and annotator_ids required")

    videos = db.query(Video).join(Question).filter(Question.project_id == project_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]

    users_info = []
    for aid in annotator_ids:
        user = db.query(User).filter(User.id == aid).first()
        if user:
            existing_count = db.query(Assignment).filter(Assignment.annotator_id == aid).count()
            users_info.append({
                "id": user.id,
                "name": user.display_name or user.username,
                "current_tasks": existing_count,
            })

    # Build a plan based on the instruction
    # Simple heuristic parsing for common patterns
    plan = []
    n = len(annotator_ids)

    if "均匀" in instruction or "平均" in instruction or not instruction:
        # Default: round robin
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            if annotation_mode == "single":
                plan.append({
                    "video_id": video.id,
                    "video_id_str": video.video_id,
                    "annotator_a_id": annotator_ids[a_idx],
                    "annotator_a_name": users_info[a_idx]["name"] if a_idx < len(users_info) else "",
                    "annotator_b_id": None,
                    "annotator_b_name": "-",
                })
            else:
                b_idx = (idx + 1) % n
                if b_idx == a_idx:
                    b_idx = (idx + 2) % n
                plan.append({
                    "video_id": video.id,
                    "video_id_str": video.video_id,
                    "annotator_a_id": annotator_ids[a_idx],
                    "annotator_a_name": users_info[a_idx]["name"] if a_idx < len(users_info) else "",
                    "annotator_b_id": annotator_ids[b_idx],
                    "annotator_b_name": users_info[b_idx]["name"] if b_idx < len(users_info) else "",
                })
    elif "前" in instruction and "给" in instruction:
        # Pattern: "前100个给ann_01和ann_02"
        import re
        num_match = re.search(r"前(\d+)", instruction)
        count = int(num_match.group(1)) if num_match else len(unassigned)
        count = min(count, len(unassigned))
        # Use first two annotators for the specified range
        for idx in range(count):
            a_idx = 0
            b_idx = 1 if n > 1 else 0
            plan.append({
                "video_id": unassigned[idx].id,
                "video_id_str": unassigned[idx].video_id,
                "annotator_a_id": annotator_ids[a_idx],
                "annotator_a_name": users_info[a_idx]["name"] if a_idx < len(users_info) else "",
                "annotator_b_id": annotator_ids[b_idx],
                "annotator_b_name": users_info[b_idx]["name"] if b_idx < len(users_info) else "",
            })
        # Rest round-robin with remaining annotators
        remaining_ids = annotator_ids[2:] if n > 2 else annotator_ids
        rn = len(remaining_ids)
        for idx in range(count, len(unassigned)):
            ri = (idx - count)
            a_idx = ri % rn
            b_idx = (ri + 1) % rn
            if b_idx == a_idx:
                b_idx = (ri + 2) % rn
            plan.append({
                "video_id": unassigned[idx].id,
                "video_id_str": unassigned[idx].video_id,
                "annotator_a_id": remaining_ids[a_idx],
                "annotator_a_name": next((u["name"] for u in users_info if u["id"] == remaining_ids[a_idx]), ""),
                "annotator_b_id": remaining_ids[b_idx],
                "annotator_b_name": next((u["name"] for u in users_info if u["id"] == remaining_ids[b_idx]), ""),
            })
    else:
        # Fallback: workload-balanced (assign more to those with fewer current tasks)
        sorted_users = sorted(users_info, key=lambda u: u["current_tasks"])
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            b_idx = (idx + 1) % n
            if b_idx == a_idx:
                b_idx = (idx + 2) % n
            sorted_a = sorted_users[a_idx % len(sorted_users)]
            sorted_b = sorted_users[b_idx % len(sorted_users)]
            plan.append({
                "video_id": video.id,
                "video_id_str": video.video_id,
                "annotator_a_id": sorted_a["id"],
                "annotator_a_name": sorted_a["name"],
                "annotator_b_id": sorted_b["id"],
                "annotator_b_name": sorted_b["name"],
            })

    # Compute per-person summary
    per_person = {}
    for p in plan:
        a_name = p["annotator_a_name"]
        b_name = p["annotator_b_name"]
        per_person[a_name] = per_person.get(a_name, 0) + 1
        if b_name and b_name != "-":
            per_person[b_name] = per_person.get(b_name, 0) + 1

    return {
        "instruction": instruction,
        "total_to_assign": len(unassigned),
        "plan_count": len(plan),
        "per_person": per_person,
        "plan": plan[:30],
        "plan_full": plan,
    }


@router.post("/ai-confirm")
def ai_confirm_assignment(data: dict, db: Session = Depends(get_db)):
    """确认AI建议的分配方案，写入数据库"""
    plan = data.get("plan", [])
    if not plan:
        raise HTTPException(400, "empty plan")

    created = 0
    skipped = 0
    for item in plan:
        video_id = item.get("video_id")
        a_id = item.get("annotator_a_id")
        b_id = item.get("annotator_b_id")

        if not video_id or not a_id:
            skipped += 1
            continue

        existing = db.query(Assignment).filter(Assignment.video_id == video_id).count()
        if existing > 0:
            skipped += 1
            continue

        db.add(Assignment(video_id=video_id, annotator_id=a_id, role="A"))
        created += 1
        if b_id:
            db.add(Assignment(video_id=video_id, annotator_id=b_id, role="B"))
            created += 1

    db.commit()
    return {"status": "confirmed", "created": created, "skipped": skipped}


@router.get("/progress")
def get_assignment_progress(project_id: int = None, page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    query = db.query(Video)
    if project_id:
        query = query.join(Question).filter(Question.project_id == project_id)

    total = query.count()
    videos = query.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for video in videos:
        question = video.question
        assignments = db.query(Assignment).filter(Assignment.video_id == video.id).all()

        a_assign = next((a for a in assignments if a.role == "A"), None)
        b_assign = next((a for a in assignments if a.role == "B"), None)
        third_assign = next((a for a in assignments if a.role == "third"), None)

        finalized_count = db.query(FinalResult).filter(
            FinalResult.video_id == video.id,
            FinalResult.method.in_(["consensus", "majority", "expert", "single"]),
        ).count()
        total_cps = len(question.checkpoints) if question else 0

        if not a_assign and not b_assign:
            status = "未分配"
        elif a_assign and a_assign.status == "submitted" and b_assign and b_assign.status == "submitted":
            if finalized_count >= total_cps:
                status = "已定案"
            elif third_assign:
                if third_assign.status == "submitted":
                    status = "第三人已提交"
                else:
                    status = "待第三人"
            else:
                status = "比对完成"
        elif (a_assign and a_assign.status == "submitted") or (b_assign and b_assign.status == "submitted"):
            status = "A/B部分提交"
        else:
            status = "已分配待标注"

        result.append({
            "video_id": video.video_id,
            "question_id": question.question_id if question else "",
            "prompt_summary": (question.prompt[:60] + "...") if question and len(question.prompt) > 60 else (question.prompt if question else ""),
            "checkpoint_count": total_cps,
            "status": status,
            "finalized": finalized_count,
            "annotator_a": a_assign.annotator.display_name if a_assign and a_assign.annotator else None,
            "annotator_b": b_assign.annotator.display_name if b_assign and b_assign.annotator else None,
            "annotator_third": third_assign.annotator.display_name if third_assign and third_assign.annotator else None,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": result}


@router.get("/my")
def my_assignments(
    user_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
):
    if not user_id:
        raise HTTPException(400, "user_id required")
    query = db.query(Assignment).filter(Assignment.annotator_id == user_id)
    if status:
        query = query.filter(Assignment.status == status)
    assignments = query.order_by(Assignment.assigned_at.desc()).all()

    result = []
    for a in assignments:
        video = a.video
        question = video.question if video else None
        checkpoint_count = len(question.checkpoints) if question else 0

        annotated_count = db.query(Annotation).filter(Annotation.assignment_id == a.id).count()

        result.append({
            "id": a.id,
            "video_id": a.video_id,
            "role": a.role,
            "status": a.status,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "video": {
                "video_id": video.video_id if video else "",
                "oss_url": video.oss_url if video else "",
            },
            "question": {
                "question_id": question.question_id if question else "",
                "prompt": question.prompt if question else "",
            },
            "checkpoint_count": checkpoint_count,
            "annotated_count": annotated_count,
        })

    return result


@router.get("/{assignment_id}")
def get_assignment_detail(assignment_id: int, db: Session = Depends(get_db)):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(404, "assignment not found")

    video = a.video
    question = video.question
    checkpoints = db.query(Checkpoint).filter(Checkpoint.question_id == question.id).order_by(Checkpoint.seq).all()

    from app.services.comparator import get_disagreed_checkpoints
    disagreed_ids = []
    if a.role == "third":
        disagreed_ids = get_disagreed_checkpoints(db, video.id)

    cp_list = []
    for cp in checkpoints:
        is_disagreed = cp.id in disagreed_ids
        cp_list.append({
            "id": cp.id,
            "checkpoint_id": cp.checkpoint_id,
            "seq": cp.seq,
            "text": cp.text,
            "min_success_line": cp.min_success_line,
            "ability_id": cp.ability_id,
            "ability_name": cp.ability_name,
            "tag_id": cp.tag_id,
            "tag_name": cp.tag_name,
            "evidence_period": cp.evidence_period,
            "needs_annotation": a.role != "third" or is_disagreed,
            "is_finalized": a.role == "third" and not is_disagreed,
        })

    return {
        "assignment": {
            "id": a.id,
            "role": a.role,
            "status": a.status,
        },
        "video": {
            "id": video.id,
            "video_id": video.video_id,
            "oss_url": video.oss_url,
            "duration_sec": video.duration_sec,
        },
        "question": {
            "id": question.id,
            "question_id": question.question_id,
            "prompt": question.prompt,
        },
        "checkpoints": cp_list,
    }
