from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import FinalResult, Checkpoint, Assignment, Annotation, Video


SCORE_MAP = {"C": 1.0, "R": 0.3, "N": 0.0, "NA": None}


def compute_ability_scores(db: Session, project_id: int = None, batch_id: int = None) -> list[dict]:
    from app.models import EvalBatch

    # Check if this is a PE batch
    is_pe = False
    if batch_id:
        batch = db.query(EvalBatch).filter(EvalBatch.id == batch_id).first()
        if batch and batch.eval_mode == "pe":
            is_pe = True

    if is_pe:
        return _compute_pe_ability_scores(db, batch_id)

    # Base mode: use FinalResult
    query = db.query(
        Checkpoint.ability_id,
        Checkpoint.ability_name,
        FinalResult.final_score,
    ).join(
        FinalResult, FinalResult.checkpoint_id == Checkpoint.id
    )

    if batch_id:
        query = query.join(Video, FinalResult.video_id == Video.id).filter(Video.batch_id == batch_id)
    elif project_id:
        from app.models import Question
        query = query.join(Question, Checkpoint.question_id == Question.id).filter(
            Question.project_id == project_id
        )

    query = query.filter(FinalResult.final_score.in_(["C", "R", "N"]))
    rows = query.all()

    ability_data = {}
    for ability_id, ability_name, score in rows:
        if not ability_id:
            continue
        if ability_id not in ability_data:
            ability_data[ability_id] = {
                "ability_id": ability_id,
                "ability_name": ability_name or "",
                "scores": [],
                "c_count": 0,
                "r_count": 0,
                "n_count": 0,
            }
        numeric = SCORE_MAP.get(score, 0)
        ability_data[ability_id]["scores"].append(numeric)
        if score == "C":
            ability_data[ability_id]["c_count"] += 1
        elif score == "R":
            ability_data[ability_id]["r_count"] += 1
        else:
            ability_data[ability_id]["n_count"] += 1

    # Ensure all 30 abilities are present (even if no data yet)
    all_abilities = db.query(Checkpoint.ability_id, Checkpoint.ability_name).filter(
        Checkpoint.ability_id.isnot(None)
    ).distinct().all()

    for ability_id, ability_name in all_abilities:
        if ability_id not in ability_data:
            ability_data[ability_id] = {
                "ability_id": ability_id,
                "ability_name": ability_name or "",
                "scores": [],
                "c_count": 0,
                "r_count": 0,
                "n_count": 0,
            }

    results = []
    for aid in sorted(ability_data.keys()):
        d = ability_data[aid]
        n = len(d["scores"])
        avg = (sum(d["scores"]) / n * 100) if n > 0 else 0

        if n >= 10:
            coverage = "正式排名"
        elif n >= 5:
            coverage = "初步趋势"
        elif n > 0:
            coverage = "证据不足"
        else:
            coverage = "暂无数据"

        results.append({
            "ability_id": d["ability_id"],
            "ability_name": d["ability_name"],
            "score": round(avg, 1),
            "c_count": d["c_count"],
            "r_count": d["r_count"],
            "n_count": d["n_count"],
            "total_n": n,
            "coverage_status": coverage,
        })

    results.sort(key=lambda x: x["score"])
    return results


def _compute_pe_ability_scores(db: Session, batch_id: int) -> list[dict]:
    """PE模式：直接从Annotation计算B视频的能力得分（不依赖FinalResult）"""
    from collections import defaultdict

    # Query all submitted annotations for this PE batch with target=B
    query = db.query(
        Checkpoint.ability_id,
        Checkpoint.ability_name,
        Annotation.score,
        Annotation.target,
    ).join(
        Annotation, Annotation.checkpoint_id == Checkpoint.id
    ).join(
        Assignment, Annotation.assignment_id == Assignment.id
    ).join(
        Video, Assignment.video_id == Video.id
    ).filter(
        Video.batch_id == batch_id,
        Assignment.status == "submitted",
        Annotation.score.in_(["C", "R", "N"]),
        Annotation.target.in_(["A", "B"]),
    )

    rows = query.all()

    # Group by ability + target
    ability_data = defaultdict(lambda: {
        "ability_name": "", "a_scores": [], "b_scores": [],
        "b_c": 0, "b_r": 0, "b_n": 0,
    })

    for ability_id, ability_name, score, target in rows:
        if not ability_id:
            continue
        ability_data[ability_id]["ability_name"] = ability_name or ""
        numeric = SCORE_MAP.get(score, 0)
        if target == "A":
            ability_data[ability_id]["a_scores"].append(numeric)
        else:
            ability_data[ability_id]["b_scores"].append(numeric)
            if score == "C": ability_data[ability_id]["b_c"] += 1
            elif score == "R": ability_data[ability_id]["b_r"] += 1
            else: ability_data[ability_id]["b_n"] += 1

    results = []
    for aid in sorted(ability_data.keys()):
        d = ability_data[aid]
        b_n = len(d["b_scores"])
        a_n = len(d["a_scores"])
        b_score = round(sum(d["b_scores"]) / b_n * 100, 1) if b_n > 0 else 0
        a_score = round(sum(d["a_scores"]) / a_n * 100, 1) if a_n > 0 else 0
        delta = round(b_score - a_score, 1)

        if b_n >= 10:
            coverage = "正式排名"
        elif b_n >= 5:
            coverage = "初步趋势"
        else:
            coverage = "证据不足"

        results.append({
            "ability_id": aid,
            "ability_name": d["ability_name"],
            "score": b_score,
            "a_score": a_score,
            "delta": delta,
            "c_count": d["b_c"],
            "r_count": d["b_r"],
            "n_count": d["b_n"],
            "total_n": b_n,
            "coverage_status": coverage,
        })

    results.sort(key=lambda x: x["score"])
    return results


def compute_module_scores(db: Session, batch_id: int = None) -> dict:
    """按模块（视频/声音/同步）计算得分，仅对 T2AV 有意义"""
    abilities = compute_ability_scores(db, batch_id=batch_id)

    modules = {
        "visual": {"name": "视频层", "prefix": "C", "scores": []},
        "audio": {"name": "声音层", "prefix": "A", "scores": []},
        "av_sync": {"name": "音画同步层", "prefix": "AV", "scores": []},
    }

    for ab in abilities:
        aid = ab["ability_id"] or ""
        score = ab["score"]
        if ab["total_n"] == 0:
            continue
        if aid.startswith("AV"):
            modules["av_sync"]["scores"].append(score)
        elif aid.startswith("A"):
            modules["audio"]["scores"].append(score)
        elif aid.startswith("C"):
            modules["visual"]["scores"].append(score)

    result = {}
    for key, mod in modules.items():
        scores = mod["scores"]
        result[key] = {
            "name": mod["name"],
            "score": round(sum(scores) / len(scores), 1) if scores else 0,
            "ability_count": len(scores),
        }

    # 综合分 = 三模块等权 1/3
    mod_scores = [result[k]["score"] for k in ["visual", "audio", "av_sync"] if result[k]["ability_count"] > 0]
    result["overall"] = round(sum(mod_scores) / len(mod_scores), 1) if mod_scores else 0

    return result


def compute_annotation_quality(db: Session, project_id: int = None, batch_id: int = None) -> dict:
    from app.models import Question

    query = db.query(Assignment).filter(Assignment.status == "submitted")
    if batch_id:
        query = query.join(Video).filter(Video.batch_id == batch_id)
    elif project_id:
        query = query.join(Video).join(Question).filter(Question.project_id == project_id)

    all_assignments = query.all()
    video_ids = set()
    for a in all_assignments:
        if a.role in ("A", "B"):
            video_ids.add(a.video_id)

    total_checkpoints = 0
    agreed_checkpoints = 0
    third_needed = 0

    for vid in video_ids:
        a_assign = next((a for a in all_assignments if a.video_id == vid and a.role == "A"), None)
        b_assign = next((a for a in all_assignments if a.video_id == vid and a.role == "B"), None)
        if not a_assign or not b_assign:
            continue

        a_anns = {ann.checkpoint_id: ann.score for ann in a_assign.annotations}
        b_anns = {ann.checkpoint_id: ann.score for ann in b_assign.annotations}

        common = set(a_anns.keys()) & set(b_anns.keys())
        total_checkpoints += len(common)
        for cp_id in common:
            if a_anns[cp_id] == b_anns[cp_id]:
                agreed_checkpoints += 1
            else:
                third_needed += 1

    agreement_rate = (agreed_checkpoints / total_checkpoints * 100) if total_checkpoints > 0 else 0
    third_rate = (third_needed / total_checkpoints * 100) if total_checkpoints > 0 else 0

    pending_query = db.query(FinalResult).filter(FinalResult.method == "pending_expert")
    if batch_id:
        pending_query = pending_query.join(Video, FinalResult.video_id == Video.id).filter(Video.batch_id == batch_id)
    pending_expert = pending_query.count()

    return {
        "total_checkpoints_compared": total_checkpoints,
        "agreed": agreed_checkpoints,
        "agreement_rate": round(agreement_rate, 1),
        "third_needed": third_needed,
        "third_rate": round(third_rate, 1),
        "pending_expert": pending_expert,
    }
