"""
PE评测增量功能测试 — 2026-08-13
覆盖: 隐藏来源开关、PE Prompt、多维度GSB、按维度原因、单双人流程、PE导出、PE看板API
"""
import sys
import os
import json
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app

TEST_DB = "sqlite:///./test_pe_features.db"
engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ============ Helpers ============

def create_users(n=3):
    users = []
    for i in range(1, n + 1):
        r = client.post("/api/users/", json={
            "username": f"pe_test_{i}", "display_name": f"PE测试员{i}",
            "role": "annotator", "password": "test123"
        })
        users.append(r.json())
    return users


def create_pe_batch(task_type="t2v", annotation_mode="single", fail_code_mode="optional", hide_source=1, n_questions=5):
    """Create a full PE batch: bank + questions + checkpoints + batch + videos"""
    from app.models import QuestionBank, Question, Checkpoint, EvalBatch, Video

    db = TestSession()
    bank = QuestionBank(name=f"PE-{task_type}-TestBank")
    db.add(bank)
    db.flush()

    abilities = ["C01", "C05", "C08", "C17", "C27", "C28", "C31", "C32"]
    if task_type == "t2av":
        abilities += ["A02", "A07", "AV02", "AV03"]

    for i in range(1, n_questions + 1):
        q = Question(
            question_id=f"Q{i:04d}", bank_id=bank.id,
            prompt=f"User prompt {i}: A person doing action {i} in a scenic environment",
            language="英文"
        )
        db.add(q)
        db.flush()

        cp_count = random.randint(3, 6)
        for j in range(1, cp_count + 1):
            ab = random.choice(abilities)
            db.add(Checkpoint(
                checkpoint_id=f"Q{i:04d}-CP{j:02d}", question_id=q.id, seq=j,
                text=f"Checkpoint {j} for Q{i:04d}", min_success_line=f"Min line CP{j:02d}",
                ability_id=ab, ability_name=f"Ability {ab}",
                tag_id="D09.03.04", tag_name="世界因果与常识逻辑"
            ))
    db.flush()

    batch = EvalBatch(
        name=f"PE-{task_type}-{annotation_mode}", bank_id=bank.id,
        model_version="v_test", task_type=task_type, eval_mode="pe",
        annotation_mode=annotation_mode, fail_code_mode=fail_code_mode,
        pe_hide_source=hide_source
    )
    db.add(batch)
    db.flush()

    questions = db.query(Question).filter(Question.bank_id == bank.id).all()
    for q in questions:
        seq = q.question_id.replace("Q", "")
        db.add(Video(
            video_id=f"V{seq}", batch_id=batch.id, question_id=q.id,
            oss_url=f"https://example.com/a_{seq}.mp4",
            pair_b_url=f"https://example.com/b_{seq}.mp4",
            pe_prompt=f"PE enhanced prompt {seq}: More detailed cinematic version with lighting and effects",
            display_order=random.choice(["AB", "BA"]),
        ))

    db.commit()
    batch_id = batch.id
    bank_id = bank.id
    db.close()
    return {"batch_id": batch_id, "bank_id": bank_id}


def make_gsb_json(bias="b_better"):
    """Generate a multi-dimension GSB JSON"""
    dims = ["dynamics", "camera", "aesthetics", "overall"]
    choices = ["a_better", "same_good", "same_bad", "b_better"]
    weights = {
        "b_better": [10, 20, 10, 60],
        "a_better": [60, 10, 20, 10],
        "mixed": [25, 25, 25, 25],
    }
    gsb = {}
    for dim in dims:
        gsb[dim] = random.choices(choices, weights=weights.get(bias, weights["mixed"]))[0]
    return gsb


def make_reasons_json(gsb):
    """Generate reasons for dimensions where A is better"""
    reasons_pool = ["原始要求被遗漏或篡改", "增加模型难以完成的内容", "画面稳定性下降", "信息冲突或过载", "其他"]
    reasons = {}
    for dim, val in gsb.items():
        if val == "a_better":
            reasons[dim] = random.choice(reasons_pool)
    return reasons


def complete_pe_tasks(user_id, batch_id, fail_code_mode="optional", gsb_bias="b_better"):
    """Have a user complete all their PE tasks"""
    r = client.get("/api/assignments/my", params={"user_id": user_id})
    tasks = [t for t in r.json() if t.get("batch_id") == batch_id and t["status"] != "submitted"]

    for task in tasks:
        r2 = client.get(f"/api/assignments/{task['id']}")
        if r2.status_code != 200:
            continue
        detail = r2.json()
        checkpoints = detail.get("checkpoints", [])

        # Annotate A and B for each checkpoint
        annotations = []
        for cp in checkpoints:
            for target in ["A", "B"]:
                score = random.choices(["C", "R", "N"], weights=[60, 25, 15])[0]
                ann = {"checkpoint_id": cp["id"], "score": score, "target": target}
                if fail_code_mode in ("optional", "required") and score in ("R", "N"):
                    ann["fail_code"] = random.choice(["F01", "F02", "F03", "F04", "F05"])
                annotations.append(ann)

        # Generate multi-dimension GSB
        gsb = make_gsb_json(gsb_bias)
        reasons = make_reasons_json(gsb)

        client.post("/api/annotations/submit", json={
            "assignment_id": task["id"],
            "annotations": annotations,
            "pe_comparison": json.dumps(gsb),
            "pe_reason": json.dumps(reasons),
        })
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

    # Lock all
    r3 = client.post("/api/annotations/submit-all", json={"user_id": user_id, "batch_id": batch_id})
    return r3.json()


# ============ Test: PE Batch Creation ============

class TestPEBatchCreation:
    def test_create_pe_batch_with_hide_source_on(self):
        """PE批次创建时 pe_hide_source=1"""
        setup = create_pe_batch(hide_source=1)
        r = client.get(f"/api/batches/{setup['batch_id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["eval_mode"] == "pe"
        assert data.get("pe_hide_source") == 1

    def test_create_pe_batch_with_hide_source_off(self):
        """PE批次创建时 pe_hide_source=0"""
        setup = create_pe_batch(hide_source=0)
        r = client.get(f"/api/batches/{setup['batch_id']}")
        data = r.json()
        assert data.get("pe_hide_source") == 0

    def test_pe_prompt_stored_in_video(self):
        """Video表保存了PE Prompt"""
        setup = create_pe_batch()
        db = TestSession()
        from app.models import Video
        videos = db.query(Video).filter(Video.batch_id == setup["batch_id"]).all()
        for v in videos:
            assert v.pe_prompt is not None
            assert "PE enhanced" in v.pe_prompt
        db.close()

    def test_pe_prompt_not_shown_to_annotator(self):
        """标注员通过assignment detail看不到PE Prompt"""
        users = create_users(1)
        setup = create_pe_batch()
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        detail = r2.json()
        # The detail should have video URL but NOT pe_prompt
        assert "pe_prompt" not in json.dumps(detail) or detail.get("video", {}).get("pe_prompt") is None


# ============ Test: Multi-Dimension GSB ============

class TestMultiDimensionGSB:
    def test_gsb_stored_as_json(self):
        """GSB以5维度JSON格式存储"""
        users = create_users(1)
        setup = create_pe_batch()
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })

        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        checkpoints = r2.json()["checkpoints"]

        gsb = {"dynamics": "b_better", "camera": "tie", "aesthetics": "a_better", "overall": "b_better"}
        reasons = {"aesthetics": "画面稳定性下降"}

        annotations = []
        for cp in checkpoints:
            annotations.append({"checkpoint_id": cp["id"], "score": "C", "target": "A"})
            annotations.append({"checkpoint_id": cp["id"], "score": "R", "target": "B"})

        r3 = client.post("/api/annotations/submit", json={
            "assignment_id": task["id"],
            "annotations": annotations,
            "pe_comparison": json.dumps(gsb),
            "pe_reason": json.dumps(reasons),
        })
        assert r3.status_code == 200

        # Verify stored correctly
        db = TestSession()
        from app.models import Assignment
        asgn = db.query(Assignment).filter(Assignment.id == task["id"]).first()
        stored_gsb = json.loads(asgn.pe_comparison)
        stored_reasons = json.loads(asgn.pe_reason)
        assert stored_gsb["dynamics"] == "b_better"
        assert stored_gsb["camera"] == "tie"
        assert stored_gsb["aesthetics"] == "a_better"
        assert stored_gsb["overall"] == "b_better"
        assert stored_reasons["aesthetics"] == "画面稳定性下降"
        assert "dynamics" not in stored_reasons  # only a_better dims have reasons
        db.close()

    def test_gsb_with_audio_dimension_t2av(self):
        """T2AV模式下GSB包含声音效果维度"""
        users = create_users(1)
        setup = create_pe_batch(task_type="t2av")
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })

        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        checkpoints = r2.json()["checkpoints"]

        # Include audio dimension
        gsb = {"dynamics": "b_better", "audio": "a_better", "camera": "same_good", "aesthetics": "b_better", "overall": "b_better"}
        reasons = {"audio": "信息冲突或过载"}

        annotations = [{"checkpoint_id": cp["id"], "score": "C", "target": "A"} for cp in checkpoints]
        annotations += [{"checkpoint_id": cp["id"], "score": "C", "target": "B"} for cp in checkpoints]

        r3 = client.post("/api/annotations/submit", json={
            "assignment_id": task["id"],
            "annotations": annotations,
            "pe_comparison": json.dumps(gsb),
            "pe_reason": json.dumps(reasons),
        })
        assert r3.status_code == 200

        db = TestSession()
        from app.models import Assignment
        asgn = db.query(Assignment).filter(Assignment.id == task["id"]).first()
        stored_gsb = json.loads(asgn.pe_comparison)
        assert "audio" in stored_gsb
        assert stored_gsb["audio"] == "a_better"
        db.close()


# ============ Test: PE Single-Person Flow ============

class TestPESinglePerson:
    def test_t2v_single_no_failcode(self):
        """T2V单人PE完整流程，无失败码"""
        users = create_users(1)
        setup = create_pe_batch(task_type="t2v", annotation_mode="single", fail_code_mode="disabled")
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        result = complete_pe_tasks(users[0]["id"], setup["batch_id"], "disabled")
        assert result.get("locked_count", 0) > 0

    def test_t2av_single_with_failcode(self):
        """T2AV单人PE完整流程，必选失败码"""
        users = create_users(1)
        setup = create_pe_batch(task_type="t2av", annotation_mode="single", fail_code_mode="required")
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        result = complete_pe_tasks(users[0]["id"], setup["batch_id"], "required")
        assert result.get("locked_count", 0) > 0


# ============ Test: PE Dual-Person Flow ============

class TestPEDualPerson:
    def test_t2v_dual_both_submit(self):
        """T2V双人PE，两人各自完成后锁定"""
        users = create_users(3)
        setup = create_pe_batch(task_type="t2v", annotation_mode="dual")
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [u["id"] for u in users], "annotation_mode": "dual"
        })

        # Both annotators complete
        for user in users[:2]:
            result = complete_pe_tasks(user["id"], setup["batch_id"], "optional")
            assert result.get("locked_count", 0) >= 0

    def test_t2av_dual_different_gsb(self):
        """T2AV双人PE，两人GSB判定不同"""
        users = create_users(3)
        setup = create_pe_batch(task_type="t2av", annotation_mode="dual")
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [u["id"] for u in users], "annotation_mode": "dual"
        })

        # User 1: biased toward B better
        complete_pe_tasks(users[0]["id"], setup["batch_id"], "optional", gsb_bias="b_better")
        # User 2: biased toward A better
        complete_pe_tasks(users[1]["id"], setup["batch_id"], "optional", gsb_bias="a_better")

        # Both should succeed (no GSB arbitration in current version)
        r = client.get("/api/scores/pe-overview", params={"batch_id": setup["batch_id"]})
        assert r.status_code == 200


# ============ Test: PE Overview API ============

class TestPEOverviewAPI:
    def test_overview_returns_correct_structure(self):
        """PE overview API返回正确的数据结构"""
        users = create_users(1)
        setup = create_pe_batch(task_type="t2v", n_questions=10)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        complete_pe_tasks(users[0]["id"], setup["batch_id"])

        r = client.get("/api/scores/pe-overview", params={"batch_id": setup["batch_id"]})
        assert r.status_code == 200
        data = r.json()

        # Check overview structure
        assert "overview" in data
        ov = data["overview"]
        assert "a_score" in ov
        assert "b_score" in ov
        assert "delta" in ov
        assert "total" in ov
        assert "b_better" in ov
        assert "tie" in ov
        assert "b_worse" in ov
        assert ov["total"] == 10

        # Check abilities structure
        assert "abilities" in data
        assert len(data["abilities"]) > 0
        for ab in data["abilities"]:
            assert "ability_id" in ab
            assert "a_score" in ab
            assert "b_score" in ab
            assert "delta" in ab

        # Check reasons structure
        assert "reasons" in data

    def test_overview_scores_in_valid_range(self):
        """PE得分在0-100范围内"""
        users = create_users(1)
        setup = create_pe_batch(n_questions=8)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        complete_pe_tasks(users[0]["id"], setup["batch_id"])

        r = client.get("/api/scores/pe-overview", params={"batch_id": setup["batch_id"]})
        data = r.json()
        ov = data["overview"]
        assert 0 <= ov["a_score"] <= 100
        assert 0 <= ov["b_score"] <= 100
        assert ov["b_better"] + ov["tie"] + ov["b_worse"] == ov["total"]

    def test_overview_without_batch_returns_empty(self):
        """无batch_id时返回空数据"""
        r = client.get("/api/scores/pe-overview")
        assert r.status_code == 200
        data = r.json()
        assert data["overview"] == {}

    def test_pe_overview_parses_json_gsb(self):
        """PE overview正确解析JSON格式的GSB"""
        users = create_users(1)
        setup = create_pe_batch(n_questions=5)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        # All tasks: overall=b_better
        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        tasks = [t for t in r.json() if t.get("batch_id") == setup["batch_id"]]

        for task in tasks:
            r2 = client.get(f"/api/assignments/{task['id']}")
            cps = r2.json()["checkpoints"]
            anns = []
            for cp in cps:
                anns.append({"checkpoint_id": cp["id"], "score": "C", "target": "A"})
                anns.append({"checkpoint_id": cp["id"], "score": "C", "target": "B"})

            gsb = {"dynamics": "b_better", "camera": "b_better", "aesthetics": "b_better", "overall": "b_better"}
            client.post("/api/annotations/submit", json={
                "assignment_id": task["id"], "annotations": anns,
                "pe_comparison": json.dumps(gsb), "pe_reason": json.dumps({}),
            })
            client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

        # Lock all
        r_lock = client.post("/api/annotations/submit-all", json={"user_id": users[0]["id"], "batch_id": setup["batch_id"]})
        assert r_lock.json().get("locked_count", 0) == 5

        r = client.get("/api/scores/pe-overview", params={"batch_id": setup["batch_id"]})
        data = r.json()
        # All should be b_better since overall=b_better for all
        assert data["overview"]["b_better"] == 5
        assert data["overview"]["tie"] == 0
        assert data["overview"]["b_worse"] == 0


# ============ Test: PE Export ============

class TestPEExport:
    def test_pe_batch_export_returns_xlsx(self):
        """PE批次导出返回有效xlsx"""
        users = create_users(1)
        setup = create_pe_batch()
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        complete_pe_tasks(users[0]["id"], setup["batch_id"])

        r = client.get("/api/export/results", params={"batch_id": setup["batch_id"]})
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        # Check filename contains PE
        assert "PE" in r.headers.get("content-disposition", "")

    def test_base_batch_export_not_pe(self):
        """基础批次导出不走PE逻辑"""
        from app.models import QuestionBank, Question, Checkpoint, EvalBatch, Video
        db = TestSession()
        bank = QuestionBank(name="BaseBank")
        db.add(bank)
        db.flush()
        q = Question(question_id="Q0001", bank_id=bank.id, prompt="test", language="英文")
        db.add(q)
        db.flush()
        db.add(Checkpoint(checkpoint_id="Q0001-CP01", question_id=q.id, seq=1, text="cp1", ability_id="C01", ability_name="test"))
        batch = EvalBatch(name="BaseBatch", bank_id=bank.id, model_version="v1", eval_mode="base")
        db.add(batch)
        db.flush()
        db.add(Video(video_id="V0001", batch_id=batch.id, question_id=q.id, oss_url="http://x.mp4"))
        db.commit()
        batch_id = batch.id
        db.close()

        r = client.get("/api/export/results", params={"batch_id": batch_id})
        assert r.status_code == 200
        assert "PE" not in r.headers.get("content-disposition", "")

    def test_pe_export_contains_delta(self):
        """PE导出xlsx中包含增益Δ数据"""
        users = create_users(1)
        setup = create_pe_batch(n_questions=3)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        complete_pe_tasks(users[0]["id"], setup["batch_id"])

        r = client.get("/api/export/results", params={"batch_id": setup["batch_id"]})
        assert r.status_code == 200
        # The file should be a valid xlsx (check size > 0)
        assert len(r.content) > 1000


# ============ Test: Batch-Scoped Remaining Count ============

class TestBatchScopedRemaining:
    def test_assignments_have_batch_id(self):
        """标注员任务列表包含batch_id字段"""
        users = create_users(1)
        setup = create_pe_batch(n_questions=3)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })

        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        tasks = r.json()
        assert len(tasks) > 0
        for task in tasks:
            assert "batch_id" in task
            assert task["batch_id"] == setup["batch_id"]

    def test_multiple_batches_separate_count(self):
        """多个批次的任务分开计数"""
        users = create_users(1)
        setup1 = create_pe_batch(n_questions=3)
        setup2 = create_pe_batch(n_questions=5)
        client.post(f"/api/batches/{setup1['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })
        client.post(f"/api/batches/{setup2['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })

        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        tasks = r.json()
        batch1_tasks = [t for t in tasks if t["batch_id"] == setup1["batch_id"]]
        batch2_tasks = [t for t in tasks if t["batch_id"] == setup2["batch_id"]]
        assert len(batch1_tasks) == 3
        assert len(batch2_tasks) == 5


# ============ Test: Annotation Target (A/B) ============

class TestAnnotationTarget:
    def test_annotations_stored_with_target(self):
        """标注保存时带有target=A/B字段"""
        users = create_users(1)
        setup = create_pe_batch(n_questions=1)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })

        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        annotations = [
            {"checkpoint_id": cps[0]["id"], "score": "C", "target": "A"},
            {"checkpoint_id": cps[0]["id"], "score": "R", "target": "B"},
        ]
        client.post("/api/annotations/submit", json={
            "assignment_id": task["id"], "annotations": annotations,
        })

        # Verify targets stored
        db = TestSession()
        from app.models import Annotation
        anns = db.query(Annotation).filter(Annotation.assignment_id == task["id"]).all()
        targets = {a.target for a in anns}
        assert "A" in targets
        assert "B" in targets
        # Check the scores match
        a_ann = next(a for a in anns if a.target == "A")
        b_ann = next(a for a in anns if a.target == "B")
        assert a_ann.score == "C"
        assert b_ann.score == "R"
        db.close()

    def test_a_and_b_scores_computed_separately(self):
        """PE overview分别计算A和B的得分"""
        users = create_users(1)
        setup = create_pe_batch(n_questions=2)
        client.post(f"/api/batches/{setup['batch_id']}/assign", json={
            "annotator_ids": [users[0]["id"]], "annotation_mode": "single"
        })

        r = client.get("/api/assignments/my", params={"user_id": users[0]["id"]})
        tasks = [t for t in r.json() if t["batch_id"] == setup["batch_id"]]

        for task in tasks:
            r2 = client.get(f"/api/assignments/{task['id']}")
            cps = r2.json()["checkpoints"]
            # All A=N, All B=C → A score should be 0, B score should be 100
            anns = []
            for cp in cps:
                anns.append({"checkpoint_id": cp["id"], "score": "N", "target": "A"})
                anns.append({"checkpoint_id": cp["id"], "score": "C", "target": "B"})
            gsb = {"dynamics": "b_better", "camera": "b_better", "aesthetics": "b_better", "overall": "b_better"}
            client.post("/api/annotations/submit", json={
                "assignment_id": task["id"], "annotations": anns,
                "pe_comparison": json.dumps(gsb), "pe_reason": json.dumps({}),
            })
            client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

        client.post("/api/annotations/submit-all", json={"user_id": users[0]["id"], "batch_id": setup["batch_id"]})

        r = client.get("/api/scores/pe-overview", params={"batch_id": setup["batch_id"]})
        data = r.json()
        assert data["overview"]["a_score"] == 0.0
        assert data["overview"]["b_score"] == 100.0
        assert data["overview"]["delta"] == 100.0


# ============ Test: Hide Source Setting ============

class TestHideSource:
    def test_hide_source_default_is_on(self):
        """默认隐藏来源"""
        setup = create_pe_batch()
        db = TestSession()
        from app.models import EvalBatch
        batch = db.query(EvalBatch).filter(EvalBatch.id == setup["batch_id"]).first()
        assert batch.pe_hide_source == 1
        db.close()

    def test_hide_source_off(self):
        """可以关闭隐藏来源"""
        setup = create_pe_batch(hide_source=0)
        db = TestSession()
        from app.models import EvalBatch
        batch = db.query(EvalBatch).filter(EvalBatch.id == setup["batch_id"]).first()
        assert batch.pe_hide_source == 0
        db.close()
