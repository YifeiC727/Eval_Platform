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
