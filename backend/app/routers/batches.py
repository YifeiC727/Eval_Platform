from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EvalBatch, QuestionBank, Question, Checkpoint, Video, Assignment, Annotation, FinalResult, User, BatchMember

router = APIRouter(prefix="/api/batches", tags=["eval-batches"])


@router.get("/")
def list_batches(db: Session = Depends(get_db)):
    batches = db.query(EvalBatch).order_by(EvalBatch.created_at.desc()).all()
    result = []
    for b in batches:
        total_videos = db.query(func.count(Video.id)).filter(Video.batch_id == b.id).scalar()
        assigned_videos = db.query(func.count(func.distinct(Assignment.video_id))).join(Video).filter(Video.batch_id == b.id).scalar()
        total_assignments = db.query(func.count(Assignment.id)).join(Video).filter(Video.batch_id == b.id).scalar()
        submitted = db.query(func.count(Assignment.id)).join(Video).filter(
            Video.batch_id == b.id, Assignment.status == "submitted"
        ).scalar()
        finalized = db.query(func.count(FinalResult.id)).join(Video).filter(Video.batch_id == b.id).scalar()
        total_cps = db.query(func.count(Checkpoint.id)).join(Question).filter(Question.bank_id == b.bank_id).scalar()

        progress = 0
        if total_assignments > 0:
            progress = round(submitted / total_assignments * 100)

        result.append({
            "id": b.id,
            "name": b.name,
            "bank_id": b.bank_id,
            "bank_name": b.bank.name if b.bank else "",
            "model_version": b.model_version,
            "task_type": b.task_type or "t2v",
            "eval_mode": b.eval_mode or "base",
            "annotation_mode": b.annotation_mode,
            "fail_code_mode": b.fail_code_mode or "optional",
            "pe_checkpoint_mode": b.pe_checkpoint_mode or "required",
            "pe_hide_source": b.pe_hide_source if b.pe_hide_source is not None else 1,
            "status": b.status,
            "description": b.description or "",
            "total_videos": total_videos,
            "assigned_videos": assigned_videos,
            "total_assignments": total_assignments,
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
        task_type=data.get("task_type", "t2v"),
        eval_mode=data.get("eval_mode", "base"),
        annotation_mode=data.get("annotation_mode", "single"),
        fail_code_mode=data.get("fail_code_mode", "optional"),
        pe_checkpoint_mode=data.get("pe_checkpoint_mode", "required"),
        pe_hide_source=data.get("pe_hide_source", 1),
        description=data.get("description", ""),
    )
    db.add(batch)
    db.flush()

    # Create video records from bank questions
    questions = db.query(Question).filter(Question.bank_id == bank_id).all()
    video_urls = data.get("video_urls", {})  # {question_id: url}
    is_pe = data.get("eval_mode") == "pe"

    for q in questions:
        seq = q.question_id.replace("Q", "")
        url = video_urls.get(q.question_id, "") or q.video_url or ""
        v = Video(
            video_id=f"V{seq}",
            batch_id=batch.id,
            question_id=q.id,
            oss_url=url,
            pair_b_url=q.pe_video_url if is_pe else None,
        )
        db.add(v)

    db.commit()
    db.refresh(batch)
    return {
        "id": batch.id,
        "name": batch.name,
        "videos_created": len(questions),
    }


@router.get("/compare")
def compare_batches(batch_a: int, batch_b: int, db: Session = Depends(get_db)):
    """对比两个批次的能力得分"""
    from app.services.scorer import compute_ability_scores
    scores_a_list = compute_ability_scores(db, batch_id=batch_a)
    scores_b_list = compute_ability_scores(db, batch_id=batch_b)
    scores_a = {s["ability_id"]: s for s in scores_a_list}
    scores_b = {s["ability_id"]: s for s in scores_b_list}

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


@router.get("/compare-pe")
def compare_pe_batches(batch_a: int, batch_b: int, db: Session = Depends(get_db)):
    """对比两个PE批次的增益Δ变化（PE v1 vs PE v2）"""
    from collections import defaultdict

    SCORE_MAP = {"C": 1.0, "R": 0.3, "N": 0.0}

    def compute_pe_deltas(bid):
        """Compute per-ability PE增益Δ for a batch"""
        videos = db.query(Video).filter(Video.batch_id == bid).all()
        ability_scores = defaultdict(lambda: {"a_scores": [], "b_scores": []})

        for video in videos:
            assignments = db.query(Assignment).filter(
                Assignment.video_id == video.id, Assignment.status == "submitted"
            ).all()
            for asgn in assignments:
                anns = db.query(Annotation).filter(Annotation.assignment_id == asgn.id).all()
                for ann in anns:
                    if ann.score not in SCORE_MAP or not ann.target:
                        continue
                    cp = ann.checkpoint
                    if not cp or not cp.ability_id:
                        continue
                    key = cp.ability_id
                    if ann.target == "A":
                        ability_scores[key]["a_scores"].append(SCORE_MAP[ann.score])
                    elif ann.target == "B":
                        ability_scores[key]["b_scores"].append(SCORE_MAP[ann.score])

        results = {}
        for aid, data in ability_scores.items():
            a_avg = sum(data["a_scores"]) / len(data["a_scores"]) * 100 if data["a_scores"] else None
            b_avg = sum(data["b_scores"]) / len(data["b_scores"]) * 100 if data["b_scores"] else None
            delta = round(b_avg - a_avg, 1) if a_avg is not None and b_avg is not None else None
            results[aid] = {"a_score": round(a_avg, 1) if a_avg else 0, "b_score": round(b_avg, 1) if b_avg else 0, "delta": delta or 0}
        return results

    ba = db.query(EvalBatch).filter(EvalBatch.id == batch_a).first()
    bb = db.query(EvalBatch).filter(EvalBatch.id == batch_b).first()

    deltas_a = compute_pe_deltas(batch_a)
    deltas_b = compute_pe_deltas(batch_b)

    all_abilities = sorted(set(list(deltas_a.keys()) + list(deltas_b.keys())))

    # Get ability names
    from app.models import Checkpoint
    ability_names = {}
    for aid in all_abilities:
        cp = db.query(Checkpoint).filter(Checkpoint.ability_id == aid).first()
        ability_names[aid] = cp.ability_name if cp else ""

    comparison = []
    for aid in all_abilities:
        da = deltas_a.get(aid, {"delta": 0, "a_score": 0, "b_score": 0})
        db_data = deltas_b.get(aid, {"delta": 0, "a_score": 0, "b_score": 0})
        comparison.append({
            "ability_id": aid,
            "ability_name": ability_names.get(aid, ""),
            "delta_a": da["delta"],
            "delta_b": db_data["delta"],
            "delta_change": round(db_data["delta"] - da["delta"], 1),
        })

    comparison.sort(key=lambda x: x["delta_change"])
    return {
        "batch_a": {"id": batch_a, "name": ba.name if ba else "", "model": ba.model_version if ba else ""},
        "batch_b": {"id": batch_b, "name": bb.name if bb else "", "model": bb.model_version if bb else ""},
        "comparison": comparison,
    }


@router.get("/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    total_videos = db.query(func.count(Video.id)).filter(Video.batch_id == batch_id).scalar()
    assigned_videos = db.query(func.count(func.distinct(Assignment.video_id))).join(Video).filter(Video.batch_id == batch_id).scalar()
    total_assignments = db.query(func.count(Assignment.id)).join(Video).filter(Video.batch_id == batch_id).scalar()
    submitted = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.status == "submitted"
    ).scalar()
    finalized = db.query(func.count(FinalResult.id)).join(Video).filter(Video.batch_id == batch_id).scalar()

    # Per-role counts
    a_total = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "A").scalar()
    b_total = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "B").scalar()
    third_total = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "third").scalar()
    expert_total = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "expert").scalar()

    a_submitted = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "A", Assignment.status == "submitted").scalar()
    b_submitted = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "B", Assignment.status == "submitted").scalar()
    third_submitted = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "third", Assignment.status == "submitted").scalar()
    expert_submitted = db.query(func.count(Assignment.id)).join(Video).filter(
        Video.batch_id == batch_id, Assignment.role == "expert", Assignment.status == "submitted").scalar()

    # 计算待分配
    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    unassigned_videos = 0
    for v in videos:
        has_a = db.query(Assignment).filter(Assignment.video_id == v.id, Assignment.role == "A").count()
        has_b = db.query(Assignment).filter(Assignment.video_id == v.id, Assignment.role == "B").count()
        if batch.annotation_mode == "dual":
            if not has_a or not has_b:
                unassigned_videos += 1
        else:
            if not has_a:
                unassigned_videos += 1

    return {
        "id": batch.id,
        "name": batch.name,
        "bank_id": batch.bank_id,
        "bank_name": batch.bank.name if batch.bank else "",
        "model_version": batch.model_version,
        "task_type": batch.task_type or "t2v",
        "eval_mode": batch.eval_mode or "base",
        "annotation_mode": batch.annotation_mode,
        "fail_code_mode": batch.fail_code_mode or "optional",
        "pe_hide_source": batch.pe_hide_source if batch.pe_hide_source is not None else 1,
        "status": batch.status,
        "description": batch.description,
        "total_videos": total_videos,
        "assigned_videos": assigned_videos,
        "total_assignments": total_assignments,
        "submitted_assignments": submitted,
        "finalized_checkpoints": finalized,
        "unassigned_videos": unassigned_videos,
        "role_stats": {
            "A": {"total": a_total, "submitted": a_submitted},
            "B": {"total": b_total, "submitted": b_submitted},
            "C": {"total": third_total, "submitted": third_submitted},
            "expert": {"total": expert_total, "submitted": expert_submitted},
        },
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


@router.post("/{batch_id}/assign-preview")
def preview_batch_assignment(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """预览分配结果（不写入）"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    annotator_ids = data.get("annotator_ids", [])
    annotation_mode = data.get("annotation_mode", batch.annotation_mode)

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]

    n = len(annotator_ids)
    if n == 0:
        return {"total_to_assign": len(unassigned), "per_person": {}}

    user_map = {}
    for aid in annotator_ids:
        user = db.query(User).filter(User.id == aid).first()
        user_map[aid] = user.display_name or user.username if user else str(aid)

    per_person = {aid: 0 for aid in annotator_ids}
    if annotation_mode == "single":
        for idx, v in enumerate(unassigned):
            per_person[annotator_ids[idx % n]] += 1
    else:
        for idx, v in enumerate(unassigned):
            a_idx = idx % n
            b_idx = (idx + 1) % n
            if b_idx == a_idx:
                b_idx = (idx + 2) % n
            per_person[annotator_ids[a_idx]] += 1
            per_person[annotator_ids[b_idx]] += 1

    per_person_named = {user_map[k]: v for k, v in per_person.items()}
    return {"total_to_assign": len(unassigned), "per_person": per_person_named}


@router.post("/{batch_id}/sync-urls")
def sync_video_urls_from_questions(batch_id: int, db: Session = Depends(get_db)):
    """从题库的 Question.video_url / pe_video_url 同步 URL 到该批次的 Video 记录"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    is_pe = batch.eval_mode == "pe"
    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    updated = 0
    for v in videos:
        changed = False
        if v.question and v.question.video_url and not v.oss_url:
            v.oss_url = v.question.video_url
            changed = True
        if is_pe and v.question and v.question.pe_video_url and not v.pair_b_url:
            v.pair_b_url = v.question.pe_video_url
            changed = True
        if changed:
            updated += 1

    db.commit()
    return {"updated": updated, "total": len(videos)}


@router.post("/{batch_id}/update-urls")
def update_video_urls(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """批量更新视频URL: {"urls": {"Q0001": "http://..."}, "pe_urls": {"Q0001": "http://..."}}"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    urls = data.get("urls", {})
    pe_urls = data.get("pe_urls", {})
    updated = 0
    for q_id, url in urls.items():
        video = db.query(Video).join(Question).filter(
            Video.batch_id == batch_id, Question.question_id == q_id
        ).first()
        if video:
            video.oss_url = url
            updated += 1

    for q_id, url in pe_urls.items():
        video = db.query(Video).join(Question).filter(
            Video.batch_id == batch_id, Question.question_id == q_id
        ).first()
        if video:
            video.pair_b_url = url
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
    annotation_mode = data.get("annotation_mode", batch.annotation_mode)
    if not annotator_ids:
        raise HTTPException(400, "annotator_ids required")

    # Update batch annotation_mode if changed
    if annotation_mode != batch.annotation_mode:
        batch.annotation_mode = annotation_mode

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]

    n = len(annotator_ids)
    created = 0

    if annotation_mode == "single":
        if n < 1:
            raise HTTPException(400, "need at least 1 annotator")
        for idx, video in enumerate(unassigned):
            db.add(Assignment(video_id=video.id, annotator_id=annotator_ids[idx % n], role="A"))
            created += 1
    else:
        if n < 2:
            raise HTTPException(400, "dual mode needs at least 2 annotators")
        third_counts = {aid: 0 for aid in annotator_ids}
        for idx, video in enumerate(unassigned):
            a_idx = idx % n
            b_idx = (idx + 1) % n
            if b_idx == a_idx:
                b_idx = (idx + 2) % n
            a_id = annotator_ids[a_idx]
            b_id = annotator_ids[b_idx]
            db.add(Assignment(video_id=video.id, annotator_id=a_id, role="A"))
            db.add(Assignment(video_id=video.id, annotator_id=b_id, role="B"))
            created += 2
            # Pre-assign third if >=3 annotators
            if n >= 3:
                candidates = [aid for aid in annotator_ids if aid != a_id and aid != b_id]
                third_id = min(candidates, key=lambda x: third_counts[x])
                db.add(Assignment(video_id=video.id, annotator_id=third_id, role="third"))
                third_counts[third_id] += 1
                created += 1

    if batch.status == "preparing":
        batch.status = "labeling"
    db.commit()

    per_person = {}
    for aid in annotator_ids:
        user = db.query(User).filter(User.id == aid).first()
        count = db.query(Assignment).join(Video).filter(Video.batch_id == batch_id, Assignment.annotator_id == aid).count()
        per_person[user.display_name or user.username] = count

    return {"created": created, "videos_assigned": len(unassigned), "per_person": per_person}


@router.post("/{batch_id}/assign-by-allocation")
def assign_by_allocation(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """分配视频任务。双人模式：全自动按总任务数负载均衡分配A/B/C。单人模式：按allocations配额分配A。"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    allocations = data.get("allocations", [])
    annotation_mode = data.get("annotation_mode", batch.annotation_mode)

    if annotation_mode != batch.annotation_mode:
        batch.annotation_mode = annotation_mode

    # 找出需要分配的视频（A/B角色不足的）
    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    incomplete_videos = []
    for v in videos:
        existing = db.query(Assignment).filter(Assignment.video_id == v.id).all()
        existing_roles = {a.role: a.annotator_id for a in existing}
        if annotation_mode == "single":
            if "A" not in existing_roles:
                incomplete_videos.append({"video": v, "existing_roles": existing_roles})
        else:
            if "A" not in existing_roles or "B" not in existing_roles:
                incomplete_videos.append({"video": v, "existing_roles": existing_roles})

    if not incomplete_videos:
        return {"created": 0, "videos_assigned": 0, "per_person": {}}

    all_annotator_ids = [a["annotator_id"] for a in allocations if a.get("count", 0) > 0]
    all_member_ids = [m.user_id for m in db.query(BatchMember).filter(BatchMember.batch_id == batch_id).all()]
    if not all_member_ids:
        all_member_ids = all_annotator_ids
    total_requested = sum(a.get("count", 0) for a in allocations)

    if annotation_mode == "single":
        # 单人模式：按配额分配
        if not allocations:
            raise HTTPException(400, "单人模式需要指定 allocations")
        if total_requested > len(incomplete_videos):
            raise HTTPException(400, f"分配总数({total_requested})超过待分配视频数({len(incomplete_videos)})")

        created = 0
        video_idx = 0
        for alloc in allocations:
            ann_id = alloc.get("annotator_id")
            count = alloc.get("count", 0)
            if not ann_id or count <= 0:
                continue
            for _ in range(count):
                if video_idx >= len(incomplete_videos):
                    break
                v_info = incomplete_videos[video_idx]
                db.add(Assignment(video_id=v_info["video"].id, annotator_id=ann_id, role="A"))
                created += 1
                video_idx += 1
        assigned_video_count = video_idx

    else:
        # 双人模式：基于总任务数(A+B+C)负载均衡分配
        partial_videos = [v for v in incomplete_videos if v["existing_roles"]]
        empty_videos = [v for v in incomplete_videos if not v["existing_roles"]]

        # Get all batch members
        batch_member_ids = [m.user_id for m in db.query(BatchMember).filter(BatchMember.batch_id == batch_id).all()]
        if not batch_member_ids:
            batch_member_ids = all_member_ids
        if len(batch_member_ids) < 2:
            raise HTTPException(400, "双人盲标至少需要2个项目成员")

        # Pre-compute current task counts per member (A+B+C total in this batch)
        task_counts = {}  # uid -> total
        role_counts = {}  # uid -> {A: n, B: n, third: n}
        for mid in batch_member_ids:
            a_n = db.query(Assignment).join(Video).filter(
                Video.batch_id == batch_id, Assignment.annotator_id == mid, Assignment.role == "A").count()
            b_n = db.query(Assignment).join(Video).filter(
                Video.batch_id == batch_id, Assignment.annotator_id == mid, Assignment.role == "B").count()
            t_n = db.query(Assignment).join(Video).filter(
                Video.batch_id == batch_id, Assignment.annotator_id == mid, Assignment.role == "third").count()
            task_counts[mid] = a_n + b_n + t_n
            role_counts[mid] = {"A": a_n, "B": b_n, "third": t_n}

        created = 0
        assigned_video_count = 0
        rr_counter = 0  # round-robin tiebreaker

        def pick_by_load(exclude_ids, role_hint=None):
            """选成员：排除 exclude_ids，按总任务数从低到高；并列按该角色数从低到高；仍并列轮询"""
            nonlocal rr_counter
            candidates = [mid for mid in batch_member_ids if mid not in exclude_ids]
            if not candidates:
                return None
            # Sort by (total_count, role_count, rr_index)
            def sort_key(mid):
                total = task_counts.get(mid, 0)
                role_n = role_counts.get(mid, {}).get(role_hint, 0) if role_hint else 0
                return (total, role_n)
            candidates.sort(key=sort_key)
            min_key = sort_key(candidates[0])
            tied = [c for c in candidates if sort_key(c) == min_key]
            chosen = tied[rr_counter % len(tied)]
            rr_counter += 1
            # Update counts
            task_counts[chosen] = task_counts.get(chosen, 0) + 1
            if role_hint:
                role_counts.setdefault(chosen, {"A": 0, "B": 0, "third": 0})
                role_counts[chosen][role_hint] = role_counts[chosen].get(role_hint, 0) + 1
            return chosen

        # 第一阶段：补只缺一个角色的视频
        for v_info in partial_videos:
            video = v_info["video"]
            existing_roles = v_info["existing_roles"]
            assigned_people = set(existing_roles.values())

            if "A" not in existing_roles:
                a_id = pick_by_load(exclude_ids=assigned_people, role_hint="A")
                if a_id:
                    db.add(Assignment(video_id=video.id, annotator_id=a_id, role="A"))
                    assigned_people.add(a_id)
                    created += 1
                    assigned_video_count += 1

            if "B" not in existing_roles:
                b_id = pick_by_load(exclude_ids=assigned_people, role_hint="B")
                if b_id:
                    db.add(Assignment(video_id=video.id, annotator_id=b_id, role="B"))
                    assigned_people.add(b_id)
                    created += 1
                    if "A" in existing_roles:
                        assigned_video_count += 1

            # Assign third if missing and >=3 members
            if "third" not in existing_roles and len(batch_member_ids) >= 3 and len(assigned_people) >= 2:
                t_id = pick_by_load(exclude_ids=assigned_people, role_hint="third")
                if t_id:
                    db.add(Assignment(video_id=video.id, annotator_id=t_id, role="third"))
                    created += 1

        # 第二阶段：分配完全空的视频
        for v_info in empty_videos:
            video = v_info["video"]

            a_id = pick_by_load(exclude_ids=set(), role_hint="A")
            if not a_id:
                break

            b_id = pick_by_load(exclude_ids={a_id}, role_hint="B")
            if not b_id:
                break

            db.add(Assignment(video_id=video.id, annotator_id=a_id, role="A"))
            db.add(Assignment(video_id=video.id, annotator_id=b_id, role="B"))
            created += 2
            assigned_video_count += 1

            # Pre-assign third if >=3 members
            if len(batch_member_ids) >= 3:
                t_id = pick_by_load(exclude_ids={a_id, b_id}, role_hint="third")
                if t_id:
                    db.add(Assignment(video_id=video.id, annotator_id=t_id, role="third"))
                    created += 1

    if batch.status == "preparing":
        batch.status = "labeling"
    db.commit()

    per_person = {}
    for alloc in allocations:
        user = db.query(User).filter(User.id == alloc["annotator_id"]).first()
        if user:
            count = db.query(Assignment).join(Video).filter(
                Video.batch_id == batch_id, Assignment.annotator_id == user.id
            ).count()
            per_person[user.display_name or user.username] = count

    return {"created": created, "videos_assigned": assigned_video_count, "per_person": per_person}


@router.post("/{batch_id}/ai-suggest")
def ai_suggest_batch_assignment(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """AI 解析自然语言指令，生成分配方案预览"""
    from app.services.ai_assigner import parse_assignment_instruction

    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    annotator_ids = data.get("annotator_ids", [])
    instruction = data.get("instruction", "")
    annotation_mode = data.get("annotation_mode", batch.annotation_mode)

    if not annotator_ids:
        raise HTTPException(400, "annotator_ids required")
    if not instruction.strip():
        raise HTTPException(400, "instruction required")

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    unassigned = [v for v in videos if db.query(Assignment).filter(Assignment.video_id == v.id).count() == 0]
    total = len(unassigned)

    if total == 0:
        return {"total_to_assign": 0, "per_person": {}, "plan": [], "reasoning": "没有待分配的视频"}

    annotators_info = []
    for aid in annotator_ids:
        user = db.query(User).filter(User.id == aid).first()
        if user:
            existing_count = db.query(Assignment).join(Video).filter(
                Video.batch_id == batch_id, Assignment.annotator_id == aid
            ).count()
            annotators_info.append({
                "id": user.id,
                "name": user.display_name or user.username,
                "current_tasks": existing_count,
            })

    ai_result = parse_assignment_instruction(instruction, annotators_info, total)
    allocations = ai_result["allocations"]

    # 根据 AI 返回的每人数量，生成具体的分配 plan
    plan = []
    video_idx = 0
    for alloc in allocations:
        ann_id = alloc["id"]
        ann_name = alloc["name"]
        count = alloc["count"]
        for _ in range(count):
            if video_idx >= total:
                break
            video = unassigned[video_idx]
            question = video.question
            plan.append({
                "video_id": video.id,
                "video_id_str": video.video_id,
                "question_id": question.question_id if question else "",
                "annotator_a_id": ann_id,
                "annotator_a_name": ann_name,
                "annotator_b_id": None,
                "annotator_b_name": "-",
            })
            video_idx += 1

    # 双人模式：为每个 plan 项分配 B 角色（轮转方式）
    if annotation_mode == "dual" and len(annotator_ids) >= 2:
        id_to_name = {a["id"]: a["name"] for a in annotators_info}
        for i, p in enumerate(plan):
            a_id = p["annotator_a_id"]
            candidates = [aid for aid in annotator_ids if aid != a_id]
            b_id = candidates[i % len(candidates)]
            p["annotator_b_id"] = b_id
            p["annotator_b_name"] = id_to_name.get(b_id, "")

    per_person = {}
    for p in plan:
        a_name = p["annotator_a_name"]
        per_person[a_name] = per_person.get(a_name, 0) + 1

    return {
        "instruction": instruction,
        "reasoning": ai_result.get("reasoning", ""),
        "total_to_assign": total,
        "plan_count": len(plan),
        "per_person": per_person,
        "annotation_mode": annotation_mode,
        "plan": plan[:30],
        "plan_full": plan,
    }


@router.post("/{batch_id}/ai-confirm")
def ai_confirm_batch_assignment(batch_id: int, data: dict, db: Session = Depends(get_db)):
    """确认 AI 建议的分配方案，写入数据库"""
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

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

    if batch.status == "preparing":
        batch.status = "labeling"
    db.commit()

    return {"status": "confirmed", "created": created, "skipped": skipped}


@router.get("/{batch_id}/pe-gsb")
def batch_pe_gsb(batch_id: int, db: Session = Depends(get_db)):
    """获取PE批次每道题的GSB判断汇总"""
    import json as json_lib

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()
    results = []

    for video in videos:
        question = video.question
        assignments = db.query(Assignment).filter(
            Assignment.video_id == video.id, Assignment.status == "submitted"
        ).all()

        gsb_entries = []
        for asgn in assignments:
            if not asgn.pe_comparison:
                continue
            try:
                gsb = json_lib.loads(asgn.pe_comparison)
            except:
                continue
            user = asgn.annotator
            gsb_entries.append({
                "annotator": user.display_name if user else "",
                "role": asgn.role,
                "gsb": gsb,
            })

        if gsb_entries:
            results.append({
                "video_id": video.video_id,
                "question_id": question.question_id if question else "",
                "prompt": (question.prompt[:80] + "...") if question and len(question.prompt) > 80 else (question.prompt if question else ""),
                "gsb_entries": gsb_entries,
            })

    return results


@router.get("/{batch_id}/scores")
def batch_scores(batch_id: int, db: Session = Depends(get_db)):
    """获取某批次的能力得分（自动区分base/pe模式）"""
    from app.services.scorer import compute_ability_scores
    return compute_ability_scores(db, batch_id=batch_id)
    return scores


# ==================== Batch Members ====================

@router.get("/{batch_id}/members")
def list_members(batch_id: int, db: Session = Depends(get_db)):
    members = db.query(BatchMember).filter(BatchMember.batch_id == batch_id).all()
    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        task_count = db.query(Assignment).join(Video).filter(
            Video.batch_id == batch_id, Assignment.annotator_id == m.user_id
        ).count()
        result.append({
            "id": m.id,
            "user_id": m.user_id,
            "username": user.username if user else "",
            "display_name": user.display_name if user else "",
            "role": user.role if user else "",
            "task_count": task_count,
            "added_at": m.added_at.isoformat() if m.added_at else None,
        })
    return result


@router.post("/{batch_id}/members")
def add_members(batch_id: int, data: dict, db: Session = Depends(get_db)):
    batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "batch not found")

    user_ids = data.get("user_ids", [])
    added = 0
    for uid in user_ids:
        existing = db.query(BatchMember).filter(
            BatchMember.batch_id == batch_id, BatchMember.user_id == uid
        ).first()
        if not existing:
            db.add(BatchMember(batch_id=batch_id, user_id=uid))
            added += 1

    db.commit()
    return {"added": added, "total": db.query(BatchMember).filter(BatchMember.batch_id == batch_id).count()}


@router.delete("/{batch_id}/members/{user_id}")
def remove_member(batch_id: int, user_id: int, db: Session = Depends(get_db)):
    member = db.query(BatchMember).filter(
        BatchMember.batch_id == batch_id, BatchMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(404, "member not found")
    db.delete(member)
    db.commit()
    return {"status": "removed"}
