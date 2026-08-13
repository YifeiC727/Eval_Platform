from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.scorer import compute_ability_scores, compute_annotation_quality, compute_module_scores
from app.models import FinalResult, Checkpoint, Video
from collections import Counter

router = APIRouter(prefix="/api/scores", tags=["scores"])


@router.get("/abilities")
def get_ability_scores(project_id: int = None, batch_id: int = None, db: Session = Depends(get_db)):
    return compute_ability_scores(db, project_id, batch_id)


@router.get("/quality")
def get_annotation_quality(project_id: int = None, batch_id: int = None, db: Session = Depends(get_db)):
    return compute_annotation_quality(db, project_id, batch_id)


@router.get("/modules")
def get_module_scores(batch_id: int = None, db: Session = Depends(get_db)):
    return compute_module_scores(db, batch_id)


@router.get("/fail-codes")
def get_fail_code_distribution(project_id: int = None, batch_id: int = None, db: Session = Depends(get_db)):
    query = db.query(FinalResult.final_fail_code).filter(
        FinalResult.final_fail_code.isnot(None),
        FinalResult.final_fail_code != "",
    )
    if batch_id:
        query = query.join(Video, FinalResult.video_id == Video.id).filter(Video.batch_id == batch_id)
    elif project_id:
        from app.models import Question
        query = query.join(Checkpoint, FinalResult.checkpoint_id == Checkpoint.id).join(
            Question, Checkpoint.question_id == Question.id
        ).filter(Question.project_id == project_id)

    codes = [r[0] for r in query.all()]
    dist = Counter(codes)

    code_names = {
        "F01": "要求遗漏", "F02": "语义/指令错误", "F03": "数量/绑定错误",
        "F04": "结构/解剖错误", "F05": "动作动态错误", "F06": "交互/接触错误",
        "F07": "物理/因果错误", "F08": "时序错误", "F09": "一致性错误",
        "F10": "镜头/构图错误", "F11": "视觉呈现错误",
        "F010": "镜头/构图错误", "F011": "视觉呈现错误",
        "RF01": "内容/类型错误", "RF02": "数量、身份或角色绑定错误",
        "RF03": "时序、顺序或同步错误", "RF04": "音质伪影",
        "RF05": "连续性错误", "RF06": "混音层级错误", "RF07": "空间声错误",
        "N1": "目标声音缺失", "N2": "完全错误或无关", "N3": "严重崩坏不可辨",
    }

    return [
        {"code": code, "name": code_names.get(code, ""), "count": count}
        for code, count in sorted(dist.items())
    ]


@router.get("/tags")
def get_tag_scores(project_id: int = None, batch_id: int = None, db: Session = Depends(get_db)):
    query = db.query(
        Checkpoint.tag_id,
        Checkpoint.tag_name,
        FinalResult.final_score,
    ).join(FinalResult, FinalResult.checkpoint_id == Checkpoint.id)

    if batch_id:
        query = query.join(Video, FinalResult.video_id == Video.id).filter(Video.batch_id == batch_id)
    elif project_id:
        from app.models import Question
        query = query.join(Question, Checkpoint.question_id == Question.id).filter(
            Question.project_id == project_id
        )

    query = query.filter(FinalResult.final_score.in_(["C", "R", "N"]))
    rows = query.all()

    tag_data = {}
    score_map = {"C": 1.0, "R": 0.3, "N": 0.0}

    for tag_id, tag_name, score in rows:
        if not tag_id:
            continue
        if tag_id not in tag_data:
            tag_data[tag_id] = {"tag_id": tag_id, "tag_name": tag_name or "", "scores": [], "c": 0, "r": 0, "n": 0}
        tag_data[tag_id]["scores"].append(score_map.get(score, 0))
        if score == "C":
            tag_data[tag_id]["c"] += 1
        elif score == "R":
            tag_data[tag_id]["r"] += 1
        else:
            tag_data[tag_id]["n"] += 1

    results = []
    for tid in sorted(tag_data.keys()):
        d = tag_data[tid]
        n = len(d["scores"])
        results.append({
            "tag_id": d["tag_id"],
            "tag_name": d["tag_name"],
            "score": round(sum(d["scores"]) / n * 100, 1) if n > 0 else 0,
            "c_count": d["c"],
            "r_count": d["r"],
            "n_count": d["n"],
            "total_n": n,
        })

    results.sort(key=lambda x: x["score"])
    return results


@router.get("/pe-overview")
def get_pe_overview(batch_id: int = None, db: Session = Depends(get_db)):
    """PE评测专用看板数据：总览指标 + 能力增益 + 原因分布"""
    from app.models import Assignment, Annotation, Question
    from collections import defaultdict

    if not batch_id:
        return {"overview": {}, "abilities": [], "reasons": []}

    SCORE_MAP = {"C": 1.0, "R": 0.3, "N": 0.0}

    videos = db.query(Video).filter(Video.batch_id == batch_id).all()

    # Per-question A/B scores + comparison
    question_data = []
    ability_a = defaultdict(lambda: {"name": "", "scores": []})
    ability_b = defaultdict(lambda: {"name": "", "scores": []})

    for video in videos:
        q = video.question
        if not q:
            continue

        assignments = db.query(Assignment).filter(
            Assignment.video_id == video.id,
            Assignment.status == "submitted",
        ).all()

        a_scores = []
        b_scores = []
        pe_comparison = None
        pe_reason = None

        for asgn in assignments:
            if asgn.pe_comparison:
                # Parse JSON GSB: extract "overall" dimension as the headline comparison
                try:
                    import json as _json
                    gsb = _json.loads(asgn.pe_comparison)
                    pe_comparison = gsb.get("overall", "tie")
                except (ValueError, TypeError):
                    pe_comparison = asgn.pe_comparison
            if asgn.pe_reason:
                try:
                    import json as _json
                    reasons = _json.loads(asgn.pe_reason)
                    pe_reason = reasons.get("overall") or next(iter(reasons.values()), None) if isinstance(reasons, dict) else asgn.pe_reason
                except (ValueError, TypeError):
                    pe_reason = asgn.pe_reason

            anns = db.query(Annotation).filter(Annotation.assignment_id == asgn.id).all()
            for ann in anns:
                if ann.score not in SCORE_MAP:
                    continue
                cp = ann.checkpoint
                if not cp:
                    continue
                aid = cp.ability_id or "UNKNOWN"

                if ann.target == "A":
                    a_scores.append(SCORE_MAP[ann.score])
                    ability_a[aid]["name"] = cp.ability_name or ""
                    ability_a[aid]["scores"].append(SCORE_MAP[ann.score])
                elif ann.target == "B":
                    b_scores.append(SCORE_MAP[ann.score])
                    ability_b[aid]["name"] = cp.ability_name or ""
                    ability_b[aid]["scores"].append(SCORE_MAP[ann.score])

        if a_scores or b_scores:
            a_avg = sum(a_scores) / len(a_scores) * 100 if a_scores else None
            b_avg = sum(b_scores) / len(b_scores) * 100 if b_scores else None
            question_data.append({
                "a_score": a_avg,
                "b_score": b_avg,
                "comparison": pe_comparison,
                "reason": pe_reason,
            })

    # Summary
    valid = [q for q in question_data if q["a_score"] is not None and q["b_score"] is not None]
    total = len(valid)

    if total > 0:
        avg_a = round(sum(q["a_score"] for q in valid) / total, 1)
        avg_b = round(sum(q["b_score"] for q in valid) / total, 1)
        delta = round(avg_b - avg_a, 1)
        b_better = sum(1 for q in valid if q["comparison"] in ("B_better", "b_better"))
        tie = sum(1 for q in valid if q["comparison"] in ("tie", "same_good", "same_bad"))
        b_worse = sum(1 for q in valid if q["comparison"] in ("B_worse", "b_worse", "a_better", "A_better"))
        if b_better + tie + b_worse == 0:
            b_better = sum(1 for q in valid if q["b_score"] - q["a_score"] > 5)
            tie = sum(1 for q in valid if abs(q["b_score"] - q["a_score"]) <= 5)
            b_worse = sum(1 for q in valid if q["a_score"] - q["b_score"] > 5)
    else:
        avg_a = avg_b = delta = 0
        b_better = tie = b_worse = 0

    overview = {
        "a_score": avg_a, "b_score": avg_b, "delta": delta,
        "total": total, "b_better": b_better, "tie": tie, "b_worse": b_worse,
    }

    # Per-ability
    all_aids = sorted(set(list(ability_a.keys()) + list(ability_b.keys())))
    abilities_result = []
    for aid in all_aids:
        a_data = ability_a[aid]
        b_data = ability_b[aid]
        a_n = len(a_data["scores"])
        b_n = len(b_data["scores"])
        a_s = round(sum(a_data["scores"]) / a_n * 100, 1) if a_n else None
        b_s = round(sum(b_data["scores"]) / b_n * 100, 1) if b_n else None
        d = round(b_s - a_s, 1) if (a_s is not None and b_s is not None) else None
        abilities_result.append({
            "ability_id": aid, "ability_name": a_data["name"] or b_data["name"],
            "a_score": a_s, "b_score": b_s, "delta": d, "a_n": a_n, "b_n": b_n,
        })
    abilities_result.sort(key=lambda x: x["delta"] if x["delta"] is not None else 0)

    # Reasons
    PE_BETTER_REASONS = ["动作与动态张力", "镜头运动", "构图/光影/材质/风格", "分镜/转场/叙事", "稳定性与整体完成度"]
    PE_WORSE_REASONS = ["原始要求被遗漏或篡改", "增加模型难以完成的内容", "画面稳定性下降", "信息冲突或过载", "其他"]

    reason_counter = Counter(q["reason"] for q in question_data if q["reason"])
    reasons_result = []
    for reason, count in reason_counter.most_common():
        rtype = "better" if reason in PE_BETTER_REASONS else "worse"
        reasons_result.append({
            "reason": reason, "count": count,
            "pct": f"{round(count/total*100, 1)}%" if total else "0%",
            "type": rtype,
        })

    return {"overview": overview, "abilities": abilities_result, "reasons": reasons_result}
