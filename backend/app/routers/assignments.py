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


@router.post("/reset-single")
def reset_single_assignment(data: dict, db: Session = Depends(get_db)):
    """重置单道题的标注。若重置A/B则级联清除third/expert和FinalResult。"""
    video_id_str = data.get("video_id")
    annotator_name = data.get("annotator")

    if not video_id_str:
        raise HTTPException(400, "video_id required")

    video = db.query(Video).filter(Video.video_id == video_id_str).first()
    if not video:
        raise HTTPException(404, "video not found")

    query = db.query(Assignment).filter(Assignment.video_id == video.id)
    if annotator_name:
        user = db.query(User).filter(
            (User.display_name == annotator_name) | (User.username == annotator_name)
        ).first()
        if user:
            query = query.filter(Assignment.annotator_id == user.id)

    assignments = query.all()
    deleted = 0

    # Check if any A/B is being reset → cascade
    has_ab_reset = any(a.role in ("A", "B") for a in assignments)
    has_third_reset = any(a.role == "third" for a in assignments)

    for a in assignments:
        db.query(Annotation).filter(Annotation.assignment_id == a.id).delete(synchronize_session=False)
        db.delete(a)
        deleted += 1

    # Cascade: if A/B reset, also remove third + expert + all FinalResults
    if has_ab_reset:
        downstream = db.query(Assignment).filter(
            Assignment.video_id == video.id,
            Assignment.role.in_(["third", "expert"]),
        ).all()
        for d in downstream:
            db.query(Annotation).filter(Annotation.assignment_id == d.id).delete(synchronize_session=False)
            db.delete(d)
            deleted += 1
        db.query(FinalResult).filter(FinalResult.video_id == video.id).delete(synchronize_session=False)
    elif has_third_reset:
        # Remove expert + pending_expert FinalResults
        expert_assigns = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.role == "expert"
        ).all()
        for e in expert_assigns:
            db.query(Annotation).filter(Annotation.assignment_id == e.id).delete(synchronize_session=False)
            db.delete(e)
            deleted += 1
        db.query(FinalResult).filter(
            FinalResult.video_id == video.id,
            FinalResult.method.in_(["pending_expert", "expert", "majority"]),
        ).delete(synchronize_session=False)
    else:
        # Resetting expert only: remove its FinalResults
        db.query(FinalResult).filter(FinalResult.video_id == video.id).delete(synchronize_session=False)

    db.commit()
    return {"status": "reset", "deleted_assignments": deleted, "video_id": video_id_str}


@router.post("/reset-single-by-annotator")
def reset_by_annotator_in_batch(data: dict, db: Session = Depends(get_db)):
    """移除某标注员在某批次中的所有任务。如果移除的是A/B，级联清除该视频的third/expert和FinalResult。"""
    batch_id = data.get("batch_id")
    annotator_name = data.get("annotator_name")

    if not batch_id or not annotator_name:
        raise HTTPException(400, "batch_id and annotator_name required")

    user = db.query(User).filter(
        (User.display_name == annotator_name) | (User.username == annotator_name)
    ).first()
    if not user:
        raise HTTPException(404, "annotator not found")

    video_ids = [v.id for v in db.query(Video).filter(Video.batch_id == batch_id).all()]
    assignments = db.query(Assignment).filter(
        Assignment.video_id.in_(video_ids),
        Assignment.annotator_id == user.id,
    ).all()

    deleted = 0
    cascade_deleted = 0
    for a in assignments:
        db.query(Annotation).filter(Annotation.assignment_id == a.id).delete(synchronize_session=False)
        db.query(FinalResult).filter(FinalResult.video_id == a.video_id).delete(synchronize_session=False)

        # If removing A or B, cascade delete third and expert for this video
        if a.role in ("A", "B"):
            downstream = db.query(Assignment).filter(
                Assignment.video_id == a.video_id,
                Assignment.role.in_(["third", "expert"]),
            ).all()
            for d in downstream:
                db.query(Annotation).filter(Annotation.assignment_id == d.id).delete(synchronize_session=False)
                db.delete(d)
                cascade_deleted += 1

        # If removing third, cascade delete expert for this video
        if a.role == "third":
            expert_assigns = db.query(Assignment).filter(
                Assignment.video_id == a.video_id,
                Assignment.role == "expert",
            ).all()
            for e in expert_assigns:
                db.query(Annotation).filter(Annotation.assignment_id == e.id).delete(synchronize_session=False)
                db.delete(e)
                cascade_deleted += 1

        db.delete(a)
        deleted += 1

    db.commit()
    return {"status": "removed", "deleted": deleted, "cascade_deleted": cascade_deleted, "annotator": annotator_name}


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
def get_assignment_progress(project_id: int = None, batch_id: int = None, page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    query = db.query(Video)
    if batch_id:
        query = query.filter(Video.batch_id == batch_id)
    elif project_id:
        query = query.join(Question).filter(Question.bank_id == project_id)

    total = query.count()
    videos = query.offset((page - 1) * page_size).limit(page_size).all()

    from app.services.comparator import get_disagreed_checkpoints

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
        dropped_count = db.query(FinalResult).filter(
            FinalResult.video_id == video.id, FinalResult.method == "dropped"
        ).count()

        if not a_assign and not b_assign:
            status = "未分配"
        elif dropped_count > 0:
            status = "已废弃"
        elif finalized_count >= total_cps and total_cps > 0:
            status = "已定案"
        elif a_assign and a_assign.status == "submitted" and b_assign and b_assign.status == "submitted":
            if third_assign:
                if third_assign.status == "submitted":
                    status = "待专家" if finalized_count < total_cps else "已定案"
                elif third_assign.status == "issue_reported":
                    status = "第三人报无效"
                else:
                    status = "待第三人"
            else:
                status = "比对完成"
        elif (a_assign and a_assign.status == "issue_reported") and (b_assign and b_assign.status == "issue_reported"):
            if third_assign:
                if third_assign.status == "submitted":
                    status = "待定案"
                elif third_assign.status == "issue_reported":
                    status = "全部报无效(待管理员)"
                else:
                    status = "待第三人确认"
            else:
                status = "双人报无效(待确认)"
        elif (a_assign and a_assign.status == "issue_reported") or (b_assign and b_assign.status == "issue_reported"):
            other_status = b_assign.status if (a_assign and a_assign.status == "issue_reported") else a_assign.status
            if other_status == "submitted":
                status = "技术无效(部分)"
            else:
                status = "技术无效(A/B部分提交)"
        elif (a_assign and a_assign.status == "submitted") or (b_assign and b_assign.status == "submitted"):
            status = "A/B部分提交"
        else:
            status = "已分配待标注"

        # Compute arbitration_status
        arbitration_status = None
        both_submitted = (
            a_assign and a_assign.status == "submitted"
            and b_assign and b_assign.status == "submitted"
        )
        if status == "已定案" or status == "已废弃":
            arbitration_status = "resolved" if third_assign and third_assign.status == "submitted" else None
        elif both_submitted:
            has_disagreement = len(get_disagreed_checkpoints(db, video.id)) > 0
            if not has_disagreement:
                arbitration_status = None
            elif not third_assign:
                arbitration_status = "unassigned"
            elif third_assign.status == "submitted":
                if finalized_count >= total_cps:
                    arbitration_status = "resolved"
                else:
                    arbitration_status = "submitted"
            else:
                arbitration_status = "pending"
        elif third_assign and third_assign.status != "pending":
            arbitration_status = "waiting"

        result.append({
            "video_id": video.video_id,
            "video_db_id": video.id,
            "question_id": question.question_id if question else "",
            "prompt_summary": (question.prompt[:60] + "...") if question and len(question.prompt) > 60 else (question.prompt if question else ""),
            "checkpoint_count": total_cps,
            "status": status,
            "finalized": finalized_count,
            "arbitration_status": arbitration_status,
            "annotator_a": a_assign.annotator.display_name if a_assign and a_assign.annotator else None,
            "annotator_b": b_assign.annotator.display_name if b_assign and b_assign.annotator else None,
            "annotator_a_id": a_assign.annotator_id if a_assign else None,
            "annotator_b_id": b_assign.annotator_id if b_assign else None,
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

    from app.services.comparator import get_disagreed_checkpoints

    result = []
    for a in assignments:
        video = a.video
        question = video.question if video else None

        # Third-person visibility: only show when A/B both submitted AND disagreements exist
        if a.role == "third" and a.status != "submitted":
            a_assign = db.query(Assignment).filter(
                Assignment.video_id == a.video_id, Assignment.role == "A"
            ).first()
            b_assign = db.query(Assignment).filter(
                Assignment.video_id == a.video_id, Assignment.role == "B"
            ).first()
            both_done = (
                a_assign and a_assign.status in ("submitted", "issue_reported")
                and b_assign and b_assign.status in ("submitted", "issue_reported")
            )
            if not both_done:
                continue
            # Check if A/B reported invalid: submitted but has no annotations = was issue_reported
            a_has_anns = db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).count() > 0
            b_has_anns = db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).count() > 0
            both_invalid = (not a_has_anns and not b_has_anns)
            one_invalid = (not a_has_anns or not b_has_anns)
            if both_invalid:
                pass  # third sees all checkpoints
            elif one_invalid:
                pass  # third sees all (one side has no data)
            else:
                disagreed = get_disagreed_checkpoints(db, a.video_id)
                if not disagreed:
                    continue

        checkpoint_count = len(question.checkpoints) if question else 0
        annotated_count = db.query(Annotation).filter(Annotation.assignment_id == a.id).count()

        # For third-person, count checkpoints based on context
        if a.role == "third":
            a_assign = db.query(Assignment).filter(Assignment.video_id == a.video_id, Assignment.role == "A").first()
            b_assign = db.query(Assignment).filter(Assignment.video_id == a.video_id, Assignment.role == "B").first()
            a_has_anns = db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).count() > 0 if a_assign else False
            b_has_anns = db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).count() > 0 if b_assign else False
            if not a_has_anns or not b_has_anns:
                pass  # third sees all checkpoints (one or both invalid)
            else:
                disagreed = get_disagreed_checkpoints(db, a.video_id)
                checkpoint_count = len(disagreed)

        # For expert, count pending_expert checkpoints (or all if no pending_expert = invalid review)
        if a.role == "expert":
            from app.models import FinalResult
            pending_expert_count = db.query(FinalResult).filter(
                FinalResult.video_id == a.video_id,
                FinalResult.method == "pending_expert",
            ).count()
            if pending_expert_count > 0:
                checkpoint_count = pending_expert_count
            # else: keep full checkpoint_count (expert sees all for invalid review)

        batch = video.batch if video else None

        result.append({
            "id": a.id,
            "video_id": a.video_id,
            "role": a.role,
            "status": a.status,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "batch_id": batch.id if batch else None,
            "batch_name": batch.name if batch else "",
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
    both_ab_invalid = False
    if a.role == "third":
        # Check if A/B have no annotations (= reported invalid)
        a_assign = db.query(Assignment).filter(Assignment.video_id == video.id, Assignment.role == "A").first()
        b_assign = db.query(Assignment).filter(Assignment.video_id == video.id, Assignment.role == "B").first()
        a_has_anns = db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).count() > 0 if a_assign else False
        b_has_anns = db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).count() > 0 if b_assign else False
        both_ab_invalid = (not a_has_anns or not b_has_anns)
        if not both_ab_invalid:
            disagreed_ids = get_disagreed_checkpoints(db, video.id)

    # For expert role: show checkpoints with pending_expert OR all if no FinalResults (invalid review)
    pending_expert_ids = []
    if a.role == "expert":
        pending_expert_ids = [
            fr.checkpoint_id for fr in db.query(FinalResult).filter(
                FinalResult.video_id == video.id, FinalResult.method == "pending_expert"
            ).all()
        ]
        # If no pending_expert records, expert sees all (e.g. invalid review)
        if not pending_expert_ids:
            pending_expert_ids = [cp.id for cp in checkpoints]

    cp_list = []
    for cp in checkpoints:
        is_disagreed = cp.id in disagreed_ids
        is_pending_expert = cp.id in pending_expert_ids

        if a.role == "third":
            if both_ab_invalid:
                needs_annotation = True
                is_finalized = False
            else:
                needs_annotation = is_disagreed
                is_finalized = not is_disagreed
        elif a.role == "expert":
            needs_annotation = is_pending_expert
            is_finalized = not is_pending_expert
        else:
            needs_annotation = True
            is_finalized = False

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
            "needs_annotation": needs_annotation,
            "is_finalized": is_finalized,
        })

    # Get batch info for fail_code_mode
    batch = video.batch
    fail_code_mode = batch.fail_code_mode if batch else "optional"

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
        "batch": {
            "fail_code_mode": fail_code_mode or "optional",
        },
        "checkpoints": cp_list,
    }
