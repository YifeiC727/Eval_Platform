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
        # PE mode: unique by (assignment, checkpoint, target)
        query = db.query(Annotation).filter(
            Annotation.assignment_id == assignment.id,
            Annotation.checkpoint_id == ann_data.checkpoint_id,
        )
        if ann_data.target:
            query = query.filter(Annotation.target == ann_data.target)

        existing = query.first()

        if existing:
            existing.score = ann_data.score
            existing.fail_code = ann_data.fail_code
            existing.target = ann_data.target
            existing.evidence_ts = ann_data.evidence_ts
            existing.note = ann_data.note
            existing.submitted_at = datetime.utcnow()
        else:
            ann = Annotation(
                assignment_id=assignment.id,
                checkpoint_id=ann_data.checkpoint_id,
                score=ann_data.score,
                fail_code=ann_data.fail_code,
                target=ann_data.target,
                evidence_ts=ann_data.evidence_ts,
                note=ann_data.note,
            )
            db.add(ann)

    # Save PE comparison if provided
    pe_comparison = getattr(data, 'pe_comparison', None) or (data.__dict__.get('pe_comparison') if hasattr(data, '__dict__') else None)
    if hasattr(data, 'pe_comparison') and data.pe_comparison:
        assignment.pe_comparison = data.pe_comparison
        assignment.pe_reason = data.pe_reason if hasattr(data, 'pe_reason') else None

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
    """全部提交锁定：要求所有任务要么已完成要么技术无效。支持按批次锁定。"""
    user_id = data.get("user_id")
    batch_id = data.get("batch_id")
    if not user_id:
        raise HTTPException(400, "user_id required")

    from app.models import Video, FinalResult
    from app.services.comparator import compare_and_adjudicate, get_disagreed_checkpoints

    query = db.query(Assignment).filter(Assignment.annotator_id == user_id)
    if batch_id:
        query = query.join(Video, Assignment.video_id == Video.id).filter(Video.batch_id == batch_id)

    assignments = query.all()

    # Split into groups
    ab_assignments = [a for a in assignments if a.role in ("A", "B")]
    third_assignments = []
    for a in assignments:
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
            # Check if A/B are "invalid" by checking if they have annotations
            a_has_anns = db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).count() > 0
            b_has_anns = db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).count() > 0
            any_invalid = (not a_has_anns or not b_has_anns)
            if any_invalid or get_disagreed_checkpoints(db, a.video_id):
                third_assignments.append(a)
        elif a.role == "third" and a.status == "submitted":
            third_assignments.append(a)
    expert_assignments = [a for a in assignments if a.role == "expert"]

    # Determine which group to submit
    # Default: lock all completed assignments (A/B + visible third + expert)
    visible_assignments = ab_assignments + third_assignments + expert_assignments

    # No strict validation: just lock whatever is "completed", skip the rest

    locked = 0
    for a in visible_assignments:
        if a.status in ("completed", "issue_reported"):
            was_invalid = (a.status == "issue_reported")
            a.status = "submitted"
            a.submitted_at = datetime.utcnow()
            locked += 1
            db.flush()

            # Skip downstream logic for issue_reported (already handled by /issues/report)
            if was_invalid:
                continue

            if a.role in ("A", "B"):
                other = db.query(Assignment).filter(
                    Assignment.video_id == a.video_id,
                    Assignment.role != a.role,
                    Assignment.role.in_(["A", "B"]),
                ).first()

                if other and other.status in ("submitted", "issue_reported"):
                    # Check if other actually has annotations (vs was issue_reported)
                    other_has_anns = db.query(Annotation).filter(Annotation.assignment_id == other.id).count() > 0
                    if not other_has_anns:
                        # Other was invalid: use current person's annotations as final
                        my_anns = db.query(Annotation).filter(Annotation.assignment_id == a.id).all()
                        for ann in my_anns:
                            existing = db.query(FinalResult).filter(
                                FinalResult.video_id == a.video_id, FinalResult.checkpoint_id == ann.checkpoint_id).first()
                            if not existing:
                                db.add(FinalResult(video_id=a.video_id, checkpoint_id=ann.checkpoint_id,
                                    final_score=ann.score, final_fail_code=ann.fail_code, method="single"))
                    elif other.status == "submitted":
                        result = compare_and_adjudicate(db, a.video_id)
                        if result.get("need_third", 0) > 0:
                            existing_third = db.query(Assignment).filter(
                                Assignment.video_id == a.video_id, Assignment.role == "third").first()
                            if not existing_third:
                                from app.routers.arbitration import assign_third_person
                                assign_third_person(a.video_id, db)
                elif not other:
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

            elif a.role == "third":
                # Check if A/B both invalid (no annotations) → use third's answer directly
                a_ab = db.query(Assignment).filter(Assignment.video_id == a.video_id, Assignment.role == "A").first()
                b_ab = db.query(Assignment).filter(Assignment.video_id == a.video_id, Assignment.role == "B").first()
                a_has = db.query(Annotation).filter(Annotation.assignment_id == a_ab.id).count() > 0 if a_ab else False
                b_has = db.query(Annotation).filter(Annotation.assignment_id == b_ab.id).count() > 0 if b_ab else False
                both_invalid = (not a_has and not b_has)
                if both_invalid:
                    # Directly finalize with third's annotations
                    my_anns = db.query(Annotation).filter(Annotation.assignment_id == a.id).all()
                    for ann in my_anns:
                        existing = db.query(FinalResult).filter(
                            FinalResult.video_id == a.video_id, FinalResult.checkpoint_id == ann.checkpoint_id
                        ).first()
                        if not existing:
                            db.add(FinalResult(
                                video_id=a.video_id, checkpoint_id=ann.checkpoint_id,
                                final_score=ann.score, final_fail_code=ann.fail_code, method="single"))
                else:
                    from app.services.comparator import resolve_with_third
                    resolve_with_third(db, a.video_id)

            elif a.role == "expert":
                anns = db.query(Annotation).filter(Annotation.assignment_id == a.id).all()
                for ann in anns:
                    fr = db.query(FinalResult).filter(
                        FinalResult.video_id == a.video_id,
                        FinalResult.checkpoint_id == ann.checkpoint_id,
                        FinalResult.method == "pending_expert",
                    ).first()
                    if fr:
                        fr.final_score = ann.score
                        fr.final_fail_code = ann.fail_code
                        fr.method = "expert"

    db.commit()

    # Post-commit: run compare + resolve for any videos that now have both A/B (or third) submitted
    # This handles the case where A and B are submitted by different users in separate requests
    from app.models import Video
    if batch_id:
        video_ids = [v.id for v in db.query(Video).filter(Video.batch_id == batch_id).all()]
    else:
        video_ids = list({a.video_id for a in visible_assignments})

    for vid in video_ids:
        existing_finals = db.query(FinalResult).filter(FinalResult.video_id == vid).count()
        if existing_finals > 0:
            # Already has results, check if third needs resolution
            third_assign = db.query(Assignment).filter(
                Assignment.video_id == vid, Assignment.role == "third", Assignment.status == "submitted").first()
            if third_assign:
                from app.models import Checkpoint
                video_obj = db.query(Video).filter(Video.id == vid).first()
                total_cps = db.query(Checkpoint).filter(Checkpoint.question_id == video_obj.question_id).count()
                finalized = db.query(FinalResult).filter(
                    FinalResult.video_id == vid, FinalResult.method.in_(["consensus", "majority", "expert", "single", "dropped"])).count()
                if finalized < total_cps:
                    from app.services.comparator import resolve_with_third as _resolve
                    _resolve(db, vid)
            continue

        # No results yet - determine what to do
        a_assign = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "A").first()
        b_assign = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "B").first()
        if not a_assign or not b_assign:
            continue

        a_done = a_assign.status in ("submitted", "issue_reported")
        b_done = b_assign.status in ("submitted", "issue_reported")
        if not (a_done and b_done):
            continue

        # Determine if A/B are "truly submitted" or "was invalid" by checking annotations
        a_has_anns = db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).count() > 0
        b_has_anns = db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).count() > 0

        if a_has_anns and not b_has_anns:
            # B was invalid, use A's annotations
            anns = db.query(Annotation).filter(Annotation.assignment_id == a_assign.id).all()
            for ann in anns:
                existing = db.query(FinalResult).filter(FinalResult.video_id == vid, FinalResult.checkpoint_id == ann.checkpoint_id).first()
                if not existing:
                    db.add(FinalResult(video_id=vid, checkpoint_id=ann.checkpoint_id,
                        final_score=ann.score, final_fail_code=ann.fail_code, method="single"))
        elif b_has_anns and not a_has_anns:
            # A was invalid, use B's annotations
            anns = db.query(Annotation).filter(Annotation.assignment_id == b_assign.id).all()
            for ann in anns:
                existing = db.query(FinalResult).filter(FinalResult.video_id == vid, FinalResult.checkpoint_id == ann.checkpoint_id).first()
                if not existing:
                    db.add(FinalResult(video_id=vid, checkpoint_id=ann.checkpoint_id,
                        final_score=ann.score, final_fail_code=ann.fail_code, method="single"))
        elif not a_has_anns and not b_has_anns:
            # Both invalid → check third
            third_assign = db.query(Assignment).filter(
                Assignment.video_id == vid, Assignment.role == "third", Assignment.status == "submitted").first()
            if third_assign:
                third_has_anns = db.query(Annotation).filter(Annotation.assignment_id == third_assign.id).count() > 0
                if third_has_anns:
                    anns = db.query(Annotation).filter(Annotation.assignment_id == third_assign.id).all()
                    for ann in anns:
                        existing = db.query(FinalResult).filter(FinalResult.video_id == vid, FinalResult.checkpoint_id == ann.checkpoint_id).first()
                        if not existing:
                            db.add(FinalResult(video_id=vid, checkpoint_id=ann.checkpoint_id,
                                final_score=ann.score, final_fail_code=ann.fail_code, method="single"))
                else:
                    # Third also invalid → assign expert
                    existing_expert = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "expert").first()
                    if not existing_expert:
                        db.add(Assignment(video_id=vid, annotator_id=1, role="expert"))
        elif a_has_anns and b_has_anns:
            # Both normal → run compare
            compare_result = compare_and_adjudicate(db, vid)
            if compare_result.get("need_third", 0) > 0:
                existing_third = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "third").first()
                if not existing_third:
                    from app.routers.arbitration import assign_third_person
                    assign_third_person(vid, db)
            # Handle third invalid after compare
            third_assign = db.query(Assignment).filter(
                Assignment.video_id == vid, Assignment.role == "third", Assignment.status == "submitted").first()
            if third_assign:
                third_has_anns = db.query(Annotation).filter(Annotation.assignment_id == third_assign.id).count() > 0
                if not third_has_anns:
                    existing_expert = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "expert").first()
                    if not existing_expert:
                        db.add(Assignment(video_id=vid, annotator_id=1, role="expert"))
                    if not existing_expert:
                        db.add(Assignment(video_id=vid, annotator_id=1, role="expert"))
        elif a_assign.status == "submitted" and b_assign.status == "submitted":
            # Both submitted → run compare
            compare_result = compare_and_adjudicate(db, vid)
            if compare_result.get("need_third", 0) > 0:
                existing_third = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "third").first()
                if not existing_third:
                    from app.routers.arbitration import assign_third_person
                    assign_third_person(vid, db)
            # Handle third issue_reported after normal A/B compare
            third_invalid = db.query(Assignment).filter(
                Assignment.video_id == vid, Assignment.role == "third", Assignment.status == "issue_reported").first()
            if third_invalid:
                existing_expert = db.query(Assignment).filter(Assignment.video_id == vid, Assignment.role == "expert").first()
                if not existing_expert:
                    db.add(Assignment(video_id=vid, annotator_id=1, role="expert"))

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
            # Auto-assign third if disagreements found and no third exists
            if compare_result.get("need_third", 0) > 0:
                existing_third = db.query(Assignment).filter(
                    Assignment.video_id == assignment.video_id,
                    Assignment.role == "third",
                ).first()
                if not existing_third:
                    from app.routers.arbitration import assign_third_person
                    assign_third_person(assignment.video_id, db)
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

    if assignment.role == "expert":
        from app.models import FinalResult
        anns = db.query(Annotation).filter(Annotation.assignment_id == assignment.id).all()
        resolved = 0
        for ann in anns:
            fr = db.query(FinalResult).filter(
                FinalResult.video_id == assignment.video_id,
                FinalResult.checkpoint_id == ann.checkpoint_id,
                FinalResult.method == "pending_expert",
            ).first()
            if fr:
                fr.final_score = ann.score
                fr.final_fail_code = ann.fail_code
                fr.method = "expert"
                resolved += 1
        db.commit()
        result["expert_resolved"] = resolved

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
            "target": a.target,
            "evidence_ts": a.evidence_ts,
            "note": a.note,
        }
        for a in anns
    ]


@router.get("/compare-view/{video_db_id}")
def compare_view(video_db_id: int, db: Session = Depends(get_db)):
    """管理员查看某视频所有角色的标注对比（支持base和PE模式）"""
    from app.models import Video, Checkpoint, FinalResult

    video = db.query(Video).filter(Video.id == video_db_id).first()
    if not video:
        raise HTTPException(404, "video not found")

    question = video.question
    batch = video.batch
    eval_mode = batch.eval_mode if batch else "base"

    checkpoints = db.query(Checkpoint).filter(
        Checkpoint.question_id == question.id
    ).order_by(Checkpoint.seq).all()

    assignments = db.query(Assignment).filter(Assignment.video_id == video.id).all()
    role_map = {}
    for a in assignments:
        user = a.annotator
        anns_list = a.annotations
        # Group annotations by target (for PE mode)
        anns_by_target = {}
        anns_plain = {}
        for ann in anns_list:
            if ann.target:
                anns_by_target.setdefault(ann.target, {})[ann.checkpoint_id] = ann
            else:
                anns_plain[ann.checkpoint_id] = ann
        role_map[a.role] = {
            "annotator": user.display_name if user else "",
            "status": a.status,
            "annotations": anns_plain,
            "annotations_by_target": anns_by_target,
            "pe_comparison": a.pe_comparison,
            "pe_reason": a.pe_reason,
        }

    finals = {f.checkpoint_id: f for f in db.query(FinalResult).filter(FinalResult.video_id == video.id).all()}

    rows = []
    for cp in checkpoints:
        row = {
            "checkpoint_id": cp.checkpoint_id,
            "text": cp.text,
            "ability_name": cp.ability_name or "",
            "final_score": None,
            "final_method": None,
        }

        if eval_mode == "pe":
            # PE mode: show scores per target (A/B video) per annotator role
            for role in ("A", "B", "third", "expert"):
                if role in role_map:
                    target_anns = role_map[role]["annotations_by_target"]
                    row[f"{role}_scoreA"] = target_anns.get("A", {}).get(cp.id)
                    row[f"{role}_scoreB"] = target_anns.get("B", {}).get(cp.id)
                    if row[f"{role}_scoreA"]:
                        row[f"{role}_scoreA"] = {"score": row[f"{role}_scoreA"].score, "fail_code": row[f"{role}_scoreA"].fail_code}
                    if row[f"{role}_scoreB"]:
                        row[f"{role}_scoreB"] = {"score": row[f"{role}_scoreB"].score, "fail_code": row[f"{role}_scoreB"].fail_code}
        else:
            # Base mode: single score per annotator role
            for role in ("A", "B", "third", "expert"):
                if role in role_map:
                    ann = role_map[role]["annotations"].get(cp.id)
                    if ann:
                        row[role] = {"score": ann.score, "fail_code": ann.fail_code, "note": ann.note}
                    else:
                        row[role] = None
                else:
                    row[role] = None

        fr = finals.get(cp.id)
        if fr:
            row["final_score"] = fr.final_score
            row["final_method"] = fr.method

        rows.append(row)

    # Build PE GSB summary per annotator
    pe_gsb_summary = {}
    if eval_mode == "pe":
        for role, info in role_map.items():
            if info["pe_comparison"]:
                pe_gsb_summary[role] = {
                    "gsb": info["pe_comparison"],
                    "reason": info["pe_reason"],
                    "annotator": info["annotator"],
                }

    return {
        "video_id": video.video_id,
        "video_url": video.oss_url or "",
        "pair_b_url": video.pair_b_url or "",
        "display_order": video.display_order or "ab",
        "eval_mode": eval_mode,
        "question_id": question.question_id,
        "prompt": question.prompt,
        "roles": {role: {"annotator": info["annotator"], "status": info["status"]} for role, info in role_map.items()},
        "pe_gsb_summary": pe_gsb_summary,
        "checkpoints": rows,
    }
