import io
from collections import Counter, defaultdict
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from app.database import get_db
from app.models import FinalResult, Checkpoint, Question, Video, Assignment, Annotation, User

router = APIRouter(prefix="/api/export", tags=["export"])

SCORE_MAP = {"C": 1.0, "R": 0.3, "N": 0.0}
FAIL_CODE_NAMES = {
    "F01": "要求遗漏", "F02": "语义/指令错误", "F03": "数量/绑定错误",
    "F04": "结构/解剖错误", "F05": "动作动态错误", "F06": "交互/接触错误",
    "F07": "物理/因果错误", "F08": "时序错误", "F09": "一致性错误",
    "F10": "镜头/构图错误", "F11": "视觉呈现错误",
}


def _style_header(ws, row=1):
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="E8ECF0", end_color="E8ECF0", fill_type="solid")
    for cell in ws[row]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")


@router.get("/my-annotations")
def export_my_annotations(user_id: int = None, db: Session = Depends(get_db)):
    """标注员导出自己的标注结果"""
    if not user_id:
        return {"error": "user_id required"}

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "user not found"}

    wb = Workbook()
    ws = wb.active
    ws.title = "我的标注"
    ws.append(["题目ID", "检查点ID", "检查点内容", "最低成功线", "能力ID", "能力名称", "我的判定", "备注", "视频URL"])
    _style_header(ws)

    assignments = db.query(Assignment).filter(
        Assignment.annotator_id == user_id,
        Assignment.status.in_(["submitted", "completed"]),
    ).all()

    for assignment in assignments:
        video = assignment.video
        question = video.question if video else None
        anns = db.query(Annotation).filter(Annotation.assignment_id == assignment.id).all()
        ann_map = {a.checkpoint_id: a for a in anns}

        checkpoints = db.query(Checkpoint).filter(
            Checkpoint.question_id == question.id
        ).order_by(Checkpoint.seq).all() if question else []

        for cp in checkpoints:
            ann = ann_map.get(cp.id)
            ws.append([
                question.question_id if question else "",
                cp.checkpoint_id,
                cp.text,
                cp.min_success_line or "",
                cp.ability_id or "",
                cp.ability_name or "",
                ann.score if ann else "",
                ann.note if ann else "",
                video.oss_url if video else "",
            ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"{user.display_name or user.username}_annotations.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/results")
def export_results(project_id: int = None, db: Session = Depends(get_db)):
    wb = Workbook()

    # ========== Sheet 1: 30项能力得分 ==========
    ws1 = wb.active
    ws1.title = "能力得分排名"
    ws1.append(["能力ID", "能力名称", "得分", "C数", "R数", "N数", "有效n", "C率%", "R率%", "N率%", "覆盖状态", "主要失败码", "主要三级标签"])
    _style_header(ws1)

    # Compute ability scores
    query = db.query(Checkpoint, FinalResult).join(
        FinalResult, FinalResult.checkpoint_id == Checkpoint.id
    ).filter(FinalResult.final_score.in_(["C", "R", "N"]))
    if project_id:
        query = query.join(Question, Checkpoint.question_id == Question.id).filter(Question.project_id == project_id)

    ability_data = defaultdict(lambda: {"name": "", "scores": [], "c": 0, "r": 0, "n": 0, "fail_codes": [], "tags": []})
    for cp, fr in query.all():
        aid = cp.ability_id or "UNKNOWN"
        ability_data[aid]["name"] = cp.ability_name or ""
        ability_data[aid]["scores"].append(SCORE_MAP.get(fr.final_score, 0))
        if fr.final_score == "C":
            ability_data[aid]["c"] += 1
        elif fr.final_score == "R":
            ability_data[aid]["r"] += 1
        else:
            ability_data[aid]["n"] += 1
        if fr.final_fail_code:
            ability_data[aid]["fail_codes"].append(fr.final_fail_code)
        if cp.tag_id:
            ability_data[aid]["tags"].append(cp.tag_name or cp.tag_id)

    ability_rows = []
    for aid in sorted(ability_data.keys()):
        d = ability_data[aid]
        n = len(d["scores"])
        score = round(sum(d["scores"]) / n * 100, 1) if n > 0 else 0
        coverage = "正式排名" if n >= 10 else ("初步趋势" if n >= 5 else "证据不足")
        top_fc = Counter(d["fail_codes"]).most_common(1)
        top_tag = Counter(d["tags"]).most_common(1)
        ability_rows.append((
            aid, d["name"], score, d["c"], d["r"], d["n"], n,
            round(d["c"] / n * 100, 1) if n else 0,
            round(d["r"] / n * 100, 1) if n else 0,
            round(d["n"] / n * 100, 1) if n else 0,
            coverage,
            f'{top_fc[0][0]} {FAIL_CODE_NAMES.get(top_fc[0][0], "")}({top_fc[0][1]})' if top_fc else "",
            f'{top_tag[0][0]}({top_tag[0][1]})' if top_tag else "",
        ))

    ability_rows.sort(key=lambda x: x[2])
    for row in ability_rows:
        ws1.append(list(row))

    # ========== Sheet 2: 失败码分布 ==========
    ws2 = wb.create_sheet("失败码分布")
    ws2.append(["失败码", "名称", "次数", "占比%"])
    _style_header(ws2)

    all_fail_codes = []
    for d in ability_data.values():
        all_fail_codes.extend(d["fail_codes"])
    fc_counter = Counter(all_fail_codes)
    fc_total = sum(fc_counter.values())
    for code in sorted(fc_counter.keys()):
        ws2.append([code, FAIL_CODE_NAMES.get(code, ""), fc_counter[code],
                    round(fc_counter[code] / fc_total * 100, 1) if fc_total else 0])

    # ========== Sheet 3: 三级标签诊断 ==========
    ws3 = wb.create_sheet("三级标签诊断")
    ws3.append(["标签ID", "标签名称", "能力ID", "得分", "C数", "R数", "N数", "有效n"])
    _style_header(ws3)

    tag_data = defaultdict(lambda: {"name": "", "ability": "", "scores": [], "c": 0, "r": 0, "n": 0})
    for cp, fr in db.query(Checkpoint, FinalResult).join(
        FinalResult, FinalResult.checkpoint_id == Checkpoint.id
    ).filter(FinalResult.final_score.in_(["C", "R", "N"])).all():
        tid = cp.tag_id or "UNKNOWN"
        tag_data[tid]["name"] = cp.tag_name or ""
        tag_data[tid]["ability"] = cp.ability_id or ""
        tag_data[tid]["scores"].append(SCORE_MAP.get(fr.final_score, 0))
        if fr.final_score == "C":
            tag_data[tid]["c"] += 1
        elif fr.final_score == "R":
            tag_data[tid]["r"] += 1
        else:
            tag_data[tid]["n"] += 1

    tag_rows = []
    for tid in sorted(tag_data.keys()):
        d = tag_data[tid]
        n = len(d["scores"])
        score = round(sum(d["scores"]) / n * 100, 1) if n else 0
        tag_rows.append((tid, d["name"], d["ability"], score, d["c"], d["r"], d["n"], n))
    tag_rows.sort(key=lambda x: x[3])
    for row in tag_rows:
        ws3.append(list(row))

    # ========== Sheet 4: 标注员统计 ==========
    ws4 = wb.create_sheet("标注员统计")
    ws4.append(["标注员", "姓名", "总任务", "已提交", "完成率%", "标注总数", "C数", "R数", "N数", "C率%", "R率%", "N率%"])
    _style_header(ws4)

    annotators = db.query(User).filter(User.role.contains("annotator")).all()
    for user in annotators:
        assignments = db.query(Assignment).filter(Assignment.annotator_id == user.id).all()
        total_tasks = len(assignments)
        submitted = sum(1 for a in assignments if a.status == "submitted")

        anns = db.query(Annotation).join(Assignment).filter(Assignment.annotator_id == user.id).all()
        c_count = sum(1 for a in anns if a.score == "C")
        r_count = sum(1 for a in anns if a.score == "R")
        n_count = sum(1 for a in anns if a.score == "N")
        total_anns = c_count + r_count + n_count

        ws4.append([
            user.username, user.display_name or "",
            total_tasks, submitted,
            round(submitted / total_tasks * 100, 1) if total_tasks else 0,
            total_anns, c_count, r_count, n_count,
            round(c_count / total_anns * 100, 1) if total_anns else 0,
            round(r_count / total_anns * 100, 1) if total_anns else 0,
            round(n_count / total_anns * 100, 1) if total_anns else 0,
        ])

    # ========== Sheet 5: 题目明细 ==========
    ws5 = wb.create_sheet("题目明细")
    ws5.append(["题目ID", "Prompt", "检查点数", "题目得分", "完成率%", "C数", "R数", "N数", "主要失败能力"])
    _style_header(ws5)

    questions = db.query(Question)
    if project_id:
        questions = questions.filter(Question.project_id == project_id)

    for q in questions.all():
        cps = q.checkpoints
        q_scores = []
        q_c = q_r = q_n = 0
        fail_abilities = []
        for cp in cps:
            fr = db.query(FinalResult).filter(FinalResult.checkpoint_id == cp.id).first()
            if fr and fr.final_score in ("C", "R", "N"):
                q_scores.append(SCORE_MAP[fr.final_score])
                if fr.final_score == "C":
                    q_c += 1
                elif fr.final_score == "R":
                    q_r += 1
                else:
                    q_n += 1
                if fr.final_score in ("R", "N"):
                    fail_abilities.append(cp.ability_id or "")

        k = len(q_scores)
        total_score = sum(q_scores)
        completion = round(total_score / k * 100, 1) if k else 0
        top_fail_ability = Counter(fail_abilities).most_common(1)

        ws5.append([
            q.question_id, q.prompt[:200],
            len(cps), round(total_score, 1), completion,
            q_c, q_r, q_n,
            top_fail_ability[0][0] if top_fail_ability else "",
        ])

    # ========== Sheet 6: 最终定案明细 ==========
    ws6 = wb.create_sheet("定案明细")
    ws6.append(["视频ID", "题目ID", "检查点ID", "能力ID", "能力名称", "三级标签", "最终判定", "失败码", "定案方式", "分值"])
    _style_header(ws6)

    fr_query = db.query(FinalResult).join(Checkpoint, FinalResult.checkpoint_id == Checkpoint.id)
    if project_id:
        fr_query = fr_query.join(Question, Checkpoint.question_id == Question.id).filter(Question.project_id == project_id)

    for fr in fr_query.all():
        cp = fr.checkpoint
        q = cp.question
        v = fr.video
        ws6.append([
            v.video_id if v else "",
            q.question_id if q else "",
            cp.checkpoint_id,
            cp.ability_id or "",
            cp.ability_name or "",
            cp.tag_name or "",
            fr.final_score,
            fr.final_fail_code or "",
            fr.method,
            SCORE_MAP.get(fr.final_score, 0),
        ])

    # ========== Sheet 7: 原始标注记录 ==========
    ws7 = wb.create_sheet("原始标注")
    ws7.append(["视频ID", "题目ID", "检查点ID", "标注员", "角色", "判定", "失败码", "备注"])
    _style_header(ws7)

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
        ws7.append([
            video.video_id if video else "",
            q.question_id if q else "",
            cp.checkpoint_id if cp else "",
            user.display_name or user.username if user else "",
            asgn.role,
            ann.score,
            ann.fail_code or "",
            ann.note or "",
        ])

    # Auto-width for all sheets
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=V6_evaluation_report.xlsx"},
    )
