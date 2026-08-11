"""
V6 T2V 评测平台 — 完整端到端测试
覆盖: 用户管理、项目创建、数据导入、任务分配、标注提交、定案计算、导出
"""
import sys
import os
import io
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app

TEST_DB = "sqlite:///./test_e2e.db"
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

def create_admin():
    r = client.post("/api/users/", json={"username": "admin", "display_name": "管理员", "role": "admin", "password": "admin123"})
    return r.json()


def create_annotators(count=5):
    users = []
    for i in range(1, count + 1):
        r = client.post("/api/users/", json={
            "username": f"ann_{i:02d}",
            "display_name": f"标注员{i:02d}",
            "role": "annotator",
            "password": f"eval{i:02d}@2026",
        })
        users.append(r.json())
    return users


def create_project():
    r = client.post("/api/projects/", json={"project_id": "TEST", "name": "测试项目", "model_version": "v12"})
    return r.json()


def create_questions_and_checkpoints(db, project_id, count=10):
    """Directly insert test questions and checkpoints"""
    from app.models import Question, Checkpoint, Video, QuestionBank, EvalBatch
    # Create a bank and batch
    bank = QuestionBank(name="TestBank")
    db.add(bank)
    db.flush()
    batch = EvalBatch(name="TestBatch", bank_id=bank.id, model_version="v12")
    db.add(batch)
    db.flush()

    for i in range(1, count + 1):
        q = Question(
            question_id=f"Q{i:04d}",
            bank_id=bank.id,
            prompt=f"Test prompt {i}: A person doing action {i} in environment {i}",
            language="英文",
        )
        db.add(q)
        db.flush()

        v = Video(
            video_id=f"V{i:04d}",
            batch_id=batch.id,
            question_id=q.id,
            oss_url=f"https://example.com/video_{i:04d}.mp4",
            duration_sec=10.0,
        )
        db.add(v)

        cp_count = random.randint(3, 8)
        abilities = ["C01", "C03", "C06", "C08", "C10", "C14", "C17", "C23", "C25", "C27", "C28", "C30"]
        for j in range(1, cp_count + 1):
            ability = random.choice(abilities)
            cp = Checkpoint(
                checkpoint_id=f"Q{i:04d}-CP{j:02d}",
                question_id=q.id,
                seq=j,
                text=f"Checkpoint {j} for question {i}",
                min_success_line=f"Minimum criteria for CP{j:02d}",
                ability_id=ability,
                ability_name=f"Ability {ability}",
                tag_id=f"D{random.randint(1,15):02d}.01.01",
                tag_name=f"Tag for {ability}",
            )
            db.add(cp)

    db.commit()


# ============ Test: User Management ============

class TestUserManagement:
    def test_create_admin(self):
        admin = create_admin()
        assert admin["role"] == "admin"

    def test_create_annotators(self):
        users = create_annotators(21)
        assert len(users) == 21
        assert users[0]["username"] == "ann_01"
        assert users[20]["username"] == "ann_21"

    def test_login_with_password(self):
        create_admin()
        r = client.post("/api/users/login", json={"username": "admin", "password": "admin123", "role": "admin"})
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_login_wrong_password(self):
        create_admin()
        r = client.post("/api/users/login", json={"username": "admin", "password": "wrong", "role": "admin"})
        assert r.status_code == 401

    def test_login_no_password_set(self):
        client.post("/api/users/", json={"username": "nopw", "role": "annotator"})
        r = client.post("/api/users/login", json={"username": "nopw", "password": "123", "role": "annotator"})
        assert r.status_code == 401
        assert "未设置密码" in r.json()["detail"]

    def test_login_nonexistent_user(self):
        r = client.post("/api/users/login", json={"username": "ghost", "role": "annotator"})
        assert r.status_code == 401

    def test_multi_role_user(self):
        client.post("/api/users/", json={"username": "multi", "display_name": "多角色", "role": "admin,annotator", "password": "1234"})
        r1 = client.post("/api/users/login", json={"username": "multi", "password": "1234", "role": "admin"})
        assert r1.status_code == 200
        assert r1.json()["role"] == "admin"
        r2 = client.post("/api/users/login", json={"username": "multi", "password": "1234", "role": "annotator"})
        assert r2.status_code == 200
        assert r2.json()["role"] == "annotator"

    def test_login_wrong_role(self):
        client.post("/api/users/", json={"username": "onlyann", "role": "annotator", "password": "1234"})
        r = client.post("/api/users/login", json={"username": "onlyann", "password": "1234", "role": "admin"})
        assert r.status_code == 403

    def test_set_password(self):
        r = client.post("/api/users/", json={"username": "pwtest", "role": "annotator", "password": "old"})
        uid = r.json()["id"]
        r2 = client.put(f"/api/users/{uid}/password", json={"password": "newpass"})
        assert r2.status_code == 200
        # Old password should fail
        r3 = client.post("/api/users/login", json={"username": "pwtest", "password": "old", "role": "annotator"})
        assert r3.status_code == 401
        # New password works
        r4 = client.post("/api/users/login", json={"username": "pwtest", "password": "newpass", "role": "annotator"})
        assert r4.status_code == 200


# ============ Test: File Upload ============

class TestFileUpload:
    def test_upload_xlsx_file(self):
        """Test uploading via multipart form (same as drag-and-drop or file picker)"""
        project = create_project()
        xlsx_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                  "..", "【v6】t2v-10s_检查点拆解_含覆盖统计.xlsx")
        if not os.path.exists(xlsx_path):
            pytest.skip("Real xlsx file not available")

        with open(xlsx_path, "rb") as f:
            r = client.post("/api/import/checkpoints",
                          data={"project_id": str(project["id"])},
                          files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200
        data = r.json()
        assert data["questions"] > 0
        assert data["checkpoints"] > 0

    def test_upload_invalid_file(self):
        """Test uploading a non-xlsx file"""
        project = create_project()
        fake_file = io.BytesIO(b"this is not an xlsx file")
        r = client.post("/api/import/checkpoints",
                      data={"project_id": str(project["id"])},
                      files={"file": ("fake.xlsx", fake_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 400

    def test_upload_to_nonexistent_project(self):
        """Test uploading to a project that doesn't exist"""
        fake_file = io.BytesIO(b"data")
        r = client.post("/api/import/checkpoints",
                      data={"project_id": "999"},
                      files={"file": ("test.xlsx", fake_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 404

    def test_duplicate_import_skips(self):
        """Test that re-importing the same file skips existing records"""
        project = create_project()
        xlsx_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                  "..", "【v6】t2v-10s_检查点拆解_含覆盖统计.xlsx")
        if not os.path.exists(xlsx_path):
            pytest.skip("Real xlsx file not available")

        with open(xlsx_path, "rb") as f:
            r1 = client.post("/api/import/checkpoints",
                           data={"project_id": str(project["id"])},
                           files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

        with open(xlsx_path, "rb") as f:
            r2 = client.post("/api/import/checkpoints",
                           data={"project_id": str(project["id"])},
                           files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

        assert r2.json()["questions"] == 0
        assert r2.json()["skipped"] > 0


# ============ Test: Task Assignment ============

class TestTaskAssignment:
    def test_single_mode_assignment(self):
        project = create_project()
        annotators = create_annotators(5)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 10)
        db.close()

        r = client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 10  # 10 videos × 1 person each
        assert data["videos_assigned"] == 10

    def test_dual_mode_assignment(self):
        project = create_project()
        annotators = create_annotators(5)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 10)
        db.close()

        r = client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 20  # 10 videos × 2 people each

    def test_preview_does_not_write(self):
        project = create_project()
        annotators = create_annotators(3)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 5)
        db.close()

        r = client.post("/api/assignments/assign", json={
            "mode": "preview",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })
        assert r.json()["total_to_assign"] == 5

        # Verify nothing was written
        r2 = client.get(f"/api/assignments/my?user_id={annotators[0]['id']}")
        assert len(r2.json()) == 0

    def test_clear_assignments(self):
        project = create_project()
        annotators = create_annotators(3)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 5)
        db.close()

        client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })

        r = client.post("/api/assignments/clear", json={"project_id": project["id"]})
        assert r.json()["deleted_assignments"] == 5

    def test_no_duplicate_assignment(self):
        project = create_project()
        annotators = create_annotators(3)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 5)
        db.close()

        client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })
        # Second assign should create 0
        r = client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })
        assert r.json()["videos_assigned"] == 0


# ============ Test: Annotation Flow (21 annotators) ============

class TestAnnotationFlow:
    def _setup_full(self, annotator_count=21, question_count=21):
        project = create_project()
        annotators = create_annotators(annotator_count)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], question_count)
        db.close()

        client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })
        return project, annotators

    def test_complete_single_task(self):
        project, annotators = self._setup_full(3, 3)
        # Get first annotator's tasks
        r = client.get(f"/api/assignments/my?user_id={annotators[0]['id']}")
        tasks = r.json()
        assert len(tasks) > 0

        task = tasks[0]
        # Get assignment detail
        r2 = client.get(f"/api/assignments/{task['id']}")
        detail = r2.json()
        checkpoints = [cp for cp in detail["checkpoints"] if cp["needs_annotation"]]

        # Submit annotations
        annotations = []
        for cp in checkpoints:
            annotations.append({
                "checkpoint_id": cp["id"],
                "score": random.choice(["C", "C", "C", "R", "N"]),
            })

        r3 = client.post("/api/annotations/submit", json={
            "assignment_id": task["id"],
            "annotations": annotations,
        })
        assert r3.status_code == 200

        # Mark as complete
        r4 = client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        assert r4.json()["status"] == "completed"

    def test_submit_all_flow(self):
        """Test that submit-all locks everything and creates FinalResults"""
        project, annotators = self._setup_full(3, 3)
        ann = annotators[0]

        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        tasks = r.json()

        # Complete all tasks
        for task in tasks:
            r2 = client.get(f"/api/assignments/{task['id']}")
            detail = r2.json()
            checkpoints = [cp for cp in detail["checkpoints"] if cp["needs_annotation"]]
            annotations = [{"checkpoint_id": cp["id"], "score": "C"} for cp in checkpoints]
            client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
            client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

        # Submit all
        r3 = client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})
        assert r3.status_code == 200
        assert r3.json()["locked_count"] == len(tasks)

    def test_submit_all_fails_with_incomplete(self):
        """Submit-all should fail if there are incomplete tasks"""
        project, annotators = self._setup_full(3, 3)
        ann = annotators[0]
        r = client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})
        assert r.status_code == 400

    def test_na_not_counted_in_score(self):
        """NA annotations should not produce FinalResult"""
        project, annotators = self._setup_full(1, 1)
        ann = annotators[0]

        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        checkpoints = r2.json()["checkpoints"]

        # Mark all as NA
        annotations = [{"checkpoint_id": cp["id"], "score": "NA"} for cp in checkpoints]
        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})

        # Check scores - should be empty since everything is NA
        r3 = client.get("/api/scores/abilities")
        assert len(r3.json()) == 0

    def test_21_annotators_full_simulation(self):
        """Simulate all 21 annotators completing their tasks"""
        project, annotators = self._setup_full(21, 21)

        for ann in annotators:
            r = client.get(f"/api/assignments/my?user_id={ann['id']}")
            tasks = r.json()
            for task in tasks:
                r2 = client.get(f"/api/assignments/{task['id']}")
                detail = r2.json()
                checkpoints = [cp for cp in detail["checkpoints"] if cp["needs_annotation"]]
                annotations = []
                for cp in checkpoints:
                    score = random.choices(["C", "R", "N", "NA"], weights=[60, 25, 10, 5])[0]
                    annotations.append({"checkpoint_id": cp["id"], "score": score})
                client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
                client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
            client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})

        # Verify stats
        r = client.get("/api/stats/overview")
        overview = r.json()
        assert overview["submitted_annotations"] == 21  # 21 assignments submitted

        # Verify ability scores exist
        r2 = client.get("/api/scores/abilities")
        abilities = r2.json()
        assert len(abilities) > 0
        for a in abilities:
            assert 0 <= a["score"] <= 100
            assert a["total_n"] > 0

        # Verify annotator stats
        r3 = client.get("/api/stats/annotators")
        ann_stats = r3.json()
        assert len(ann_stats) == 21
        for s in ann_stats:
            assert s["completion_rate"] == 100.0


# ============ Test: Export ============

class TestExport:
    def test_export_results_xlsx(self):
        """Test that export returns a valid xlsx file"""
        r = client.get("/api/export/results")
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]

    def test_export_my_annotations(self):
        """Test annotator personal export"""
        project = create_project()
        annotators = create_annotators(2)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 3)
        db.close()

        client.post("/api/assignments/assign", json={
            "mode": "round_robin",
            "project_id": project["id"],
            "annotator_ids": [a["id"] for a in annotators],
            "annotation_mode": "single",
        })

        ann = annotators[0]
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        tasks = r.json()
        for task in tasks:
            r2 = client.get(f"/api/assignments/{task['id']}")
            checkpoints = r2.json()["checkpoints"]
            annotations = [{"checkpoint_id": cp["id"], "score": "C"} for cp in checkpoints]
            client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
            client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

        r3 = client.get(f"/api/export/my-annotations?user_id={ann['id']}")
        assert r3.status_code == 200
        assert "spreadsheetml" in r3.headers["content-type"]


# ============ Test: Scoring Accuracy ============

class TestScoringAccuracy:
    def test_ability_score_formula(self):
        """Verify: AbilityScore = sum(scores) / n * 100"""
        project = create_project()
        annotators = create_annotators(1)
        db = TestSession()
        # Create 1 question with 10 checkpoints all mapped to C01
        from app.models import Question, Checkpoint, Video
        q = Question(question_id="Q0001", project_id=project["id"], prompt="test", language="英文")
        db.add(q)
        db.flush()
        v = Video(video_id="V0001", question_id=q.id, model_version="v12", oss_url="http://x.mp4")
        db.add(v)
        for j in range(1, 11):
            db.add(Checkpoint(
                checkpoint_id=f"Q0001-CP{j:02d}", question_id=q.id, seq=j,
                text=f"cp{j}", ability_id="C01", ability_name="测试能力", tag_id="D01.01.01", tag_name="tag"
            ))
        db.commit()
        db.close()

        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": project["id"],
            "annotator_ids": [annotators[0]["id"]], "annotation_mode": "single",
        })

        r = client.get(f"/api/assignments/my?user_id={annotators[0]['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        # 6C + 3R + 1N = 6*1 + 3*0.3 + 1*0 = 6.9 → 69.0%
        scores = ["C"] * 6 + ["R"] * 3 + ["N"] * 1
        annotations = [{"checkpoint_id": cps[i]["id"], "score": scores[i]} for i in range(10)]
        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        client.post("/api/annotations/submit-all", json={"user_id": annotators[0]["id"]})

        r3 = client.get("/api/scores/abilities")
        abilities = r3.json()
        assert len(abilities) == 1
        assert abilities[0]["ability_id"] == "C01"
        assert abilities[0]["score"] == 69.0
        assert abilities[0]["c_count"] == 6
        assert abilities[0]["r_count"] == 3
        assert abilities[0]["n_count"] == 1
        assert abilities[0]["total_n"] == 10
        assert abilities[0]["coverage_status"] == "正式排名"


# ============ Test: Issue Reporting ============

class TestIssueReporting:
    def test_report_technical_issue(self):
        project = create_project()
        annotators = create_annotators(1)
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 2)
        db.close()

        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": project["id"],
            "annotator_ids": [annotators[0]["id"]], "annotation_mode": "single",
        })

        r = client.get(f"/api/assignments/my?user_id={annotators[0]['id']}")
        task = r.json()[0]

        r2 = client.post("/api/issues/report", json={
            "assignment_id": task["id"],
            "issue_type": "技术无效",
            "description": "视频黑屏",
        })
        assert r2.status_code == 200
        assert r2.json()["status"] == "reported"


# ============ Test: Search ============

class TestSearch:
    def test_search_by_keyword(self):
        project = create_project()
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 10)
        db.close()

        r = client.get("/api/qc/search?q=action 5")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_search_by_question_id(self):
        project = create_project()
        db = TestSession()
        create_questions_and_checkpoints(db, project["id"], 10)
        db.close()

        r = client.get("/api/qc/search?q=Q0003")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["question_id"] == "Q0003"
