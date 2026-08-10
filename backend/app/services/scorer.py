from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import FinalResult, Checkpoint, Assignment, Annotation


SCORE_MAP = {"C": 1.0, "R": 0.3, "N": 0.0, "NA": None}


def compute_ability_scores(db: Session, project_id: int = None) -> list[dict]:
    query = db.query(
        Checkpoint.ability_id,
        Checkpoint.ability_name,
        FinalResult.final_score,
    ).join(
        FinalResult, FinalResult.checkpoint_id == Checkpoint.id
    )

    if project_id:
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

    results = []
    for aid in sorted(ability_data.keys()):
        d = ability_data[aid]
        n = len(d["scores"])
        avg = (sum(d["scores"]) / n * 100) if n > 0 else 0

        if n >= 10:
            coverage = "正式排名"
        elif n >= 5:
            coverage = "初步趋势"
        else:
            coverage = "证据不足"

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


def compute_annotation_quality(db: Session, project_id: int = None) -> dict:
    from app.models import Video, Question

    query = db.query(Assignment).filter(Assignment.status == "submitted")
    if project_id:
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

    pending_expert = db.query(FinalResult).filter(FinalResult.method == "pending_expert").count()

    return {
        "total_checkpoints_compared": total_checkpoints,
        "agreed": agreed_checkpoints,
        "agreement_rate": round(agreement_rate, 1),
        "third_needed": third_needed,
        "third_rate": round(third_rate, 1),
        "pending_expert": pending_expert,
    }
