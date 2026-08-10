import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from app.database import get_db
from app.models import FinalResult, Checkpoint, Question, Video, Assignment, Annotation

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/results")
def export_results(project_id: int = None, db: Session = Depends(get_db)):
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "04_最终结果"
    ws1.append(["项目ID", "视频ID", "题目ID", "检查点ID", "最终判定", "最终失败码", "定案方式", "备注", "分值"])

    query = db.query(FinalResult).join(Checkpoint, FinalResult.checkpoint_id == Checkpoint.id)
    if project_id:
        query = query.join(Question, Checkpoint.question_id == Question.id).filter(
            Question.project_id == project_id
        )

    score_map = {"C": 1.0, "R": 0.3, "N": 0.0}

    for fr in query.all():
        cp = fr.checkpoint
        q = cp.question
        v = fr.video
        ws1.append([
            q.project_id if q else "",
            v.video_id if v else "",
            q.question_id if q else "",
            cp.checkpoint_id,
            fr.final_score,
            fr.final_fail_code or "",
            fr.method,
            fr.note or "",
            score_map.get(fr.final_score, 0),
        ])

    ws2 = wb.create_sheet("03_原始标注")
    ws2.append(["视频ID", "题目ID", "检查点ID", "标注员", "角色", "判定", "失败码", "证据时段", "备注"])

    ann_query = db.query(Annotation).join(Assignment, Annotation.assignment_id == Assignment.id)
    if project_id:
        ann_query = ann_query.join(Video, Assignment.video_id == Video.id).join(
            Question, Video.question_id == Question.id
        ).filter(Question.project_id == project_id)

    for ann in ann_query.all():
        asgn = ann.assignment
        video = asgn.video
        cp = ann.checkpoint
        q = cp.question if cp else None
        user = asgn.annotator
        ws2.append([
            video.video_id if video else "",
            q.question_id if q else "",
            cp.checkpoint_id if cp else "",
            user.username if user else "",
            asgn.role,
            ann.score,
            ann.fail_code or "",
            ann.evidence_ts or "",
            ann.note or "",
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=evaluation_results.xlsx"},
    )
