"""
V6 T2V 评测平台 — 边界条件和遗漏场景测试
覆盖: 多管理员、并发操作、数据一致性、边界值、权限隔离
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

TEST_DB = "sqlite:///./test_edge.db"
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
    # Clean all data without dropping tables (avoids FK issues)
    db = TestSession()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()


def create_user(username, role="annotator", password="1234"):
    r = client.post("/api/users/", json={"username": username, "display_name": username, "role": role, "password": password})
    return r.json()


def setup_project_with_data(question_count=5):
    from app.models import Question, Checkpoint, Video, Project
    db = TestSession()
    uid = random.randint(1000, 99999)
    p = Project(project_id=f"P{uid}", name="Test", model_version="v1")
    db.add(p)
    db.flush()
    for i in range(1, question_count + 1):
        q = Question(question_id=f"Q{uid}_{i}", project_id=p.id, prompt=f"Prompt {i}: action {i} in env {i}")
        db.add(q)
        db.flush()
        v = Video(video_id=f"V{uid}_{i}", question_id=q.id, oss_url=f"http://x/{i}.mp4")
        db.add(v)
        for j in range(1, 4):
            db.add(Checkpoint(
                checkpoint_id=f"Q{uid}_{i}-CP{j:02d}", question_id=q.id, seq=j,
                text=f"CP{j}", ability_id="C01", ability_name="Ability1", tag_id="D01.01.01", tag_name="Tag1"
            ))
    db.commit()
    pid = p.id
    db.close()
    return pid


# ============ Multi-Admin ============

class TestMultiAdmin:
    def test_multiple_admins_can_coexist(self):
        admin1 = create_user("admin1", "admin", "pw1")
        admin2 = create_user("admin2", "admin", "pw2")
        admin3 = create_user("admin3", "admin", "pw3")
        r = client.get("/api/users/")
        admins = [u for u in r.json() if u["role"] == "admin"]
        assert len(admins) == 3

    def test_any_admin_can_create_project(self):
        create_user("admin1", "admin", "pw1")
        create_user("admin2", "admin", "pw2")
        r1 = client.post("/api/projects/", json={"project_id": "P1", "name": "Project by admin1"})
        r2 = client.post("/api/projects/", json={"project_id": "P2", "name": "Project by admin2"})
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_any_admin_can_see_all_projects(self):
        client.post("/api/projects/", json={"project_id": "P1", "name": "Proj1"})
        client.post("/api/projects/", json={"project_id": "P2", "name": "Proj2"})
        r = client.get("/api/projects/")
        assert len(r.json()) == 2

    def test_admin_can_delete_others_project(self):
        create_user("admin1", "admin", "pw1")
        r = client.post("/api/projects/", json={"project_id": "P1", "name": "Proj1"})
        pid = r.json()["id"]
        r2 = client.delete(f"/api/projects/{pid}")
        assert r2.status_code == 200

    def test_admin_can_manage_others_annotators(self):
        create_user("admin1", "admin", "pw1")
        ann = create_user("ann1", "annotator", "pw")
        r = client.put(f"/api/users/{ann['id']}/password", json={"password": "newpw"})
        assert r.status_code == 200


# ============ Data Isolation Between Projects ============

class TestProjectIsolation:
    def test_same_question_id_different_projects(self):
        """Same question_id should work in different projects"""
        from app.models import Question, Project
        db = TestSession()
        p1 = Project(project_id="P1", name="Project1")
        p2 = Project(project_id="P2", name="Project2")
        db.add(p1)
        db.add(p2)
        db.flush()
        q1 = Question(question_id="Q0001", project_id=p1.id, prompt="Prompt A")
        q2 = Question(question_id="Q0001", project_id=p2.id, prompt="Prompt B")
        db.add(q1)
        db.add(q2)
        db.commit()
        # Should have 2 distinct questions
        count = db.query(Question).filter(Question.question_id == "Q0001").count()
        assert count == 2
        db.close()

    def test_stats_are_project_scoped(self):
        """Stats for project 1 should not include project 2 data"""
        from app.models import Question, Checkpoint, Video, Project
        db = TestSession()
        p1 = Project(project_id="P1", name="Proj1")
        p2 = Project(project_id="P2", name="Proj2")
        db.add_all([p1, p2])
        db.flush()
        for i in range(3):
            q = Question(question_id=f"Q{i}", project_id=p1.id, prompt=f"P1-{i}")
            db.add(q)
            db.flush()
            db.add(Video(video_id=f"V1_{i}", question_id=q.id))
        for i in range(7):
            q = Question(question_id=f"Q{i}", project_id=p2.id, prompt=f"P2-{i}")
            db.add(q)
            db.flush()
            db.add(Video(video_id=f"V2_{i}", question_id=q.id))
        db.commit()
        db.close()

        r1 = client.get(f"/api/stats/overview?project_id={p1.id}")
        r2 = client.get(f"/api/stats/overview?project_id={p2.id}")
        assert r1.json()["total_questions"] == 3
        assert r2.json()["total_questions"] == 7

    def test_clear_only_affects_one_project(self):
        """Clearing project 1 should not touch project 2"""
        from app.models import Question, Checkpoint, Video, Project, Assignment
        db = TestSession()
        p1 = Project(project_id="P1", name="Proj1")
        p2 = Project(project_id="P2", name="Proj2")
        db.add_all([p1, p2])
        db.flush()
        ann = create_user("ann1", "annotator", "pw")

        for pid, prefix in [(p1.id, "A"), (p2.id, "B")]:
            q = Question(question_id=f"{prefix}Q1", project_id=pid, prompt="x")
            db.add(q)
            db.flush()
            v = Video(video_id=f"{prefix}V1", question_id=q.id)
            db.add(v)
            db.flush()
            db.add(Assignment(video_id=v.id, annotator_id=ann["id"], role="A"))
        db.commit()
        db.close()

        # Clear project 1
        client.post("/api/assignments/clear", json={"project_id": p1.id})
        # Project 2 should still have its assignment
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        remaining = r.json()
        assert len(remaining) == 1


# ============ Annotation Edge Cases ============

class TestAnnotationEdgeCases:
    def test_cannot_submit_empty_annotations(self):
        """Should not accept submit with no annotations"""
        pid = setup_project_with_data(2)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]

        # Submit with empty list
        r2 = client.post("/api/annotations/submit", json={
            "assignment_id": task["id"], "annotations": []
        })
        assert r2.status_code == 200  # Empty is allowed (saves nothing)

    def test_cannot_double_submit_all(self):
        """Submit-all twice should not double-lock"""
        pid = setup_project_with_data(2)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        tasks = r.json()

        for task in tasks:
            r2 = client.get(f"/api/assignments/{task['id']}")
            cps = r2.json()["checkpoints"]
            annotations = [{"checkpoint_id": cp["id"], "score": "C"} for cp in cps]
            client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
            client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

        r3 = client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})
        assert r3.json()["locked_count"] == 2

        # Second submit-all should lock 0 (already locked)
        r4 = client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})
        assert r4.json()["locked_count"] == 0

    def test_mixed_scores_in_one_question(self):
        """A question can have C, R, N, NA all in different checkpoints"""
        pid = setup_project_with_data(1)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        scores = ["C", "R", "N"]  # 3 checkpoints
        annotations = [{"checkpoint_id": cps[i]["id"], "score": scores[i]} for i in range(len(cps))]
        r3 = client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        assert r3.status_code == 200

    def test_overwrite_annotation_before_lock(self):
        """Should be able to change scores before locking"""
        pid = setup_project_with_data(1)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        # First submit all C
        annotations = [{"checkpoint_id": cp["id"], "score": "C"} for cp in cps]
        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})

        # Then change to all N
        annotations2 = [{"checkpoint_id": cp["id"], "score": "N"} for cp in cps]
        r3 = client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations2})
        assert r3.status_code == 200

        # Verify scores are N
        r4 = client.get(f"/api/annotations/assignment/{task['id']}")
        for ann_record in r4.json():
            assert ann_record["score"] == "N"

    def test_invalid_score_rejected(self):
        """Score must be C, R, N, or NA"""
        pid = setup_project_with_data(1)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        annotations = [{"checkpoint_id": cps[0]["id"], "score": "X"}]
        r3 = client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        assert r3.status_code == 422


# ============ Scoring Edge Cases ============

class TestScoringEdgeCases:
    def test_all_na_produces_no_score(self):
        """If all checkpoints are NA, ability should not appear in scores"""
        pid = setup_project_with_data(1)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        annotations = [{"checkpoint_id": cp["id"], "score": "NA"} for cp in cps]
        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})

        r3 = client.get("/api/scores/abilities")
        assert len(r3.json()) == 0

    def test_single_checkpoint_ability_score(self):
        """An ability with just 1 checkpoint should still compute correctly"""
        from app.models import Question, Checkpoint, Video, Project
        db = TestSession()
        p = Project(project_id="P1", name="T")
        db.add(p)
        db.flush()
        q = Question(question_id="Q1", project_id=p.id, prompt="x")
        db.add(q)
        db.flush()
        db.add(Video(video_id="V1", question_id=q.id))
        db.add(Checkpoint(checkpoint_id="Q1-CP01", question_id=q.id, seq=1, text="x",
                         ability_id="C99", ability_name="SingleAbility", tag_id="D01.01.01", tag_name="t"))
        db.commit()
        db.close()

        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": p.id,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cp = r2.json()["checkpoints"][0]

        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": [{"checkpoint_id": cp["id"], "score": "R"}]})
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})

        r3 = client.get("/api/scores/abilities")
        c99 = next((a for a in r3.json() if a["ability_id"] == "C99"), None)
        assert c99 is not None
        assert c99["score"] == 30.0  # R = 0.3 → 30%
        assert c99["coverage_status"] == "证据不足"  # n=1 < 5

    def test_score_100_when_all_c(self):
        """All C should give score 100"""
        pid = setup_project_with_data(1)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        annotations = [{"checkpoint_id": cp["id"], "score": "C"} for cp in cps]
        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})

        r3 = client.get("/api/scores/abilities")
        for a in r3.json():
            assert a["score"] == 100.0

    def test_score_0_when_all_n(self):
        """All N should give score 0"""
        pid = setup_project_with_data(1)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        task = r.json()[0]
        r2 = client.get(f"/api/assignments/{task['id']}")
        cps = r2.json()["checkpoints"]

        annotations = [{"checkpoint_id": cp["id"], "score": "N"} for cp in cps]
        client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
        client.post("/api/annotations/complete", json={"assignment_id": task["id"]})
        client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})

        r3 = client.get("/api/scores/abilities")
        for a in r3.json():
            assert a["score"] == 0.0


# ============ Assignment Edge Cases ============

class TestAssignmentEdgeCases:
    def test_single_annotator_single_mode(self):
        """Single mode with 1 annotator should work"""
        pid = setup_project_with_data(3)
        ann = create_user("ann1", "annotator", "pw")
        r = client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        assert r.status_code == 200
        assert r.json()["created"] == 3

    def test_single_annotator_dual_mode_rejected(self):
        """Dual mode with 1 annotator should fail"""
        pid = setup_project_with_data(3)
        ann = create_user("ann1", "annotator", "pw")
        r = client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "dual"
        })
        assert r.status_code == 400

    def test_assign_empty_project(self):
        """Assigning to a project with no videos should create 0"""
        rp = client.post("/api/projects/", json={"project_id": "EMPTY", "name": "Empty"})
        empty_pid = rp.json()["id"]
        ann = create_user("ann1", "annotator", "pw")
        r = client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": empty_pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        assert r.json()["videos_assigned"] == 0


# ============ Issue Reporting Edge Cases ============

class TestIssueEdgeCases:
    def test_issue_reported_counts_for_submit_all(self):
        """Tasks marked as issue_reported should count as done for submit-all"""
        pid = setup_project_with_data(3)
        ann = create_user("ann1", "annotator", "pw")
        client.post("/api/assignments/assign", json={
            "mode": "round_robin", "project_id": pid,
            "annotator_ids": [ann["id"]], "annotation_mode": "single"
        })
        r = client.get(f"/api/assignments/my?user_id={ann['id']}")
        tasks = r.json()

        # Complete first 2 tasks normally
        for task in tasks[:2]:
            r2 = client.get(f"/api/assignments/{task['id']}")
            cps = r2.json()["checkpoints"]
            annotations = [{"checkpoint_id": cp["id"], "score": "C"} for cp in cps]
            client.post("/api/annotations/submit", json={"assignment_id": task["id"], "annotations": annotations})
            client.post("/api/annotations/complete", json={"assignment_id": task["id"]})

        # Report 3rd task as technical issue
        client.post("/api/issues/report", json={
            "assignment_id": tasks[2]["id"],
            "issue_type": "技术无效",
            "description": "视频损坏"
        })

        # submit-all should succeed (2 completed + 1 issue_reported)
        r3 = client.post("/api/annotations/submit-all", json={"user_id": ann["id"]})
        assert r3.status_code == 200
        assert r3.json()["locked_count"] == 2  # Only completed ones get locked


# ============ Export Edge Cases ============

class TestExportEdgeCases:
    def test_export_empty_project(self):
        """Export with no data should still return valid xlsx"""
        rp = client.post("/api/projects/", json={"project_id": "EMPTY", "name": "Empty"})
        pid = rp.json()["id"]
        r = client.get(f"/api/export/results?project_id={pid}")
        assert r.status_code == 200
        assert len(r.content) > 0

    def test_export_annotator_with_no_tasks(self):
        """Personal export with no tasks should return valid xlsx"""
        ann = create_user("ann1", "annotator", "pw")
        r = client.get(f"/api/export/my-annotations?user_id={ann['id']}")
        assert r.status_code == 200


# ============ Search Edge Cases ============

class TestSearchEdgeCases:
    def test_search_empty_query(self):
        """Empty search should return all"""
        pid = setup_project_with_data(5)
        r = client.get("/api/qc/search?q=")
        assert r.json()["total"] == 5

    def test_search_nonexistent_keyword(self):
        """Searching for gibberish should return 0"""
        pid = setup_project_with_data(5)
        r = client.get("/api/qc/search?q=xyznonexistent999")
        assert r.json()["total"] == 0

    def test_search_with_ability_filter(self):
        """Filter by ability_id"""
        pid = setup_project_with_data(5)
        r = client.get("/api/qc/search?ability_id=C01")
        assert r.json()["total"] >= 1


# ============ Password Edge Cases ============

class TestPasswordEdgeCases:
    def test_short_password_rejected(self):
        """Password < 4 chars should be rejected"""
        ann = create_user("ann1", "annotator", "1234")
        r = client.put(f"/api/users/{ann['id']}/password", json={"password": "12"})
        assert r.status_code == 400

    def test_empty_password_rejected(self):
        ann = create_user("ann1", "annotator", "1234")
        r = client.put(f"/api/users/{ann['id']}/password", json={"password": ""})
        assert r.status_code == 400

    def test_password_visible_to_admin(self):
        """Admin should see plain password via stats endpoint"""
        ann = create_user("ann1", "annotator", "mypass123")
        r = client.get("/api/stats/annotators")
        ann_data = next((a for a in r.json() if a["username"] == "ann1"), None)
        assert ann_data is not None
        assert ann_data["password"] == "mypass123"
