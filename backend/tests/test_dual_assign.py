"""
双人盲标分配逻辑测试
运行方式: cd backend && python -m pytest tests/test_dual_assign.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app

TEST_DB = "sqlite:///./test_dual.db"
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


def create_annotators(n):
    """创建n个标注员，返回id列表"""
    ids = []
    for i in range(n):
        r = client.post("/api/users/", json={
            "username": f"ann_{i:02d}",
            "display_name": f"标注员{i:02d}",
            "role": "annotator",
        })
        ids.append(r.json()["id"])
    return ids


def create_dual_batch(num_questions=10):
    """创建一个双人盲标批次，返回 batch_id"""
    # 创建题库
    from app.models import QuestionBank, Question, Checkpoint, Video, EvalBatch
    db = TestSession()

    bank = QuestionBank(name="测试题库", version=1)
    db.add(bank)
    db.flush()

    for i in range(1, num_questions + 1):
        q = Question(
            question_id=f"Q{i:04d}",
            bank_id=bank.id,
            prompt=f"测试prompt {i}",
        )
        db.add(q)
        db.flush()
        cp = Checkpoint(
            checkpoint_id=f"CP{i:04d}-01",
            question_id=q.id,
            seq=1,
            text=f"检查点{i}",
            min_success_line="测试成功线",
        )
        db.add(cp)

    batch = EvalBatch(
        name="双人盲标测试批次",
        bank_id=bank.id,
        model_version="test_v1",
        annotation_mode="dual",
    )
    db.add(batch)
    db.flush()

    # 创建视频
    questions = db.query(Question).filter(Question.bank_id == bank.id).all()
    for q in questions:
        v = Video(
            video_id=f"V{q.question_id[1:]}",
            batch_id=batch.id,
            question_id=q.id,
            oss_url="",
        )
        db.add(v)

    db.commit()
    batch_id = batch.id
    db.close()
    return batch_id


class TestDualAssignBasic:
    """基本双人盲标分配测试"""

    def test_assign_two_people_evenly(self):
        """两人均匀分配10题，每人主标5题"""
        ids = create_annotators(2)
        batch_id = create_dual_batch(10)

        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 5},
                {"annotator_id": ids[1], "count": 5},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200
        data = r.json()
        # 10个空视频，每个视频分A+B=创建20条assignment
        assert data["created"] == 20
        assert data["videos_assigned"] == 10

    def test_assign_three_people(self):
        """三人分配，验证每人都有任务"""
        ids = create_annotators(3)
        batch_id = create_dual_batch(9)

        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 3},
                {"annotator_id": ids[1], "count": 3},
                {"annotator_id": ids[2], "count": 3},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["videos_assigned"] == 9

    def test_reject_single_person_full_assign(self):
        """双人模式只有1人且有空视频，应拒绝"""
        ids = create_annotators(1)
        batch_id = create_dual_batch(5)

        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 5},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 400

    def test_no_self_pairing(self):
        """验证同一人不会同时是A和B"""
        ids = create_annotators(2)
        batch_id = create_dual_batch(4)

        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 2},
                {"annotator_id": ids[1], "count": 2},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200

        # 检查每个视频的A和B不是同一个人
        from app.models import Assignment, Video
        db = TestSession()
        videos = db.query(Video).filter(Video.batch_id == batch_id).all()
        for v in videos:
            assigns = db.query(Assignment).filter(Assignment.video_id == v.id).all()
            if len(assigns) == 2:
                assert assigns[0].annotator_id != assigns[1].annotator_id
        db.close()


class TestDualAssignRemoveAndReassign:
    """删除标注员后补分配测试"""

    def test_remove_annotator_and_reassign(self):
        """删除一个人后，用另一个新人补分配"""
        ids = create_annotators(4)  # 4个人，第4个是备用补分配人
        batch_id = create_dual_batch(6)

        # 先分配：前3人各2题
        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 2},
                {"annotator_id": ids[1], "count": 2},
                {"annotator_id": ids[2], "count": 2},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200

        # 确认全部分配完
        r = client.get(f"/api/batches/{batch_id}")
        assert r.json()["unassigned_videos"] == 0

        # 移除标注员0
        r = client.post("/api/assignments/reset-single-by-annotator", json={
            "batch_id": batch_id,
            "annotator_name": "标注员00",
        })
        assert r.status_code == 200

        # 待分配数应该增加
        r = client.get(f"/api/batches/{batch_id}")
        unassigned = r.json()["unassigned_videos"]
        assert unassigned > 0

        # 用新人(ids[3])补分配 — 他没参与过任何视频，不会self-pair
        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[3], "count": unassigned},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200
        assert r.json()["created"] > 0

        # 再查，应该全部分配完
        r = client.get(f"/api/batches/{batch_id}")
        assert r.json()["unassigned_videos"] == 0

    def test_partial_video_gets_b_filled(self):
        """已有A缺B的视频，补分配时应该填B角色"""
        ids = create_annotators(3)  # 第3个人作为补分配人
        batch_id = create_dual_batch(4)

        # 先正常分配（前2人）
        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 2},
                {"annotator_id": ids[1], "count": 2},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200

        # 移除标注员1
        r = client.post("/api/assignments/reset-single-by-annotator", json={
            "batch_id": batch_id,
            "annotator_name": "标注员01",
        })
        assert r.status_code == 200

        # 查看待分配数
        r = client.get(f"/api/batches/{batch_id}")
        unassigned = r.json()["unassigned_videos"]
        assert unassigned > 0

        # 用第3人来补（他没参与过，不会self-pair）
        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[2], "count": unassigned},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200
        assert r.json()["created"] > 0

        # 验证所有视频都有2条assignment
        from app.models import Assignment, Video
        db = TestSession()
        videos = db.query(Video).filter(Video.batch_id == batch_id).all()
        for v in videos:
            count = db.query(Assignment).filter(Assignment.video_id == v.id).count()
            assert count == 2, f"视频 {v.video_id} 只有 {count} 条assignment"
        db.close()


class TestDualAssignUnassignedCount:
    """待分配数统计测试"""

    def test_unassigned_count_dual_mode(self):
        """双人模式下，只有1条assignment的视频也算待分配"""
        ids = create_annotators(2)
        batch_id = create_dual_batch(4)

        # 初始：4个待分配
        r = client.get(f"/api/batches/{batch_id}")
        assert r.json()["unassigned_videos"] == 4

        # 分配完
        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 2},
                {"annotator_id": ids[1], "count": 2},
            ],
            "annotation_mode": "dual",
        })
        assert r.status_code == 200

        # 0个待分配
        r = client.get(f"/api/batches/{batch_id}")
        assert r.json()["unassigned_videos"] == 0

        # 移除一个人
        r = client.post("/api/assignments/reset-single-by-annotator", json={
            "batch_id": batch_id,
            "annotator_name": "标注员00",
        })

        # 待分配应该 > 0
        r = client.get(f"/api/batches/{batch_id}")
        assert r.json()["unassigned_videos"] > 0


class TestSingleAssign:
    """单人模式分配测试（回归）"""

    def test_single_mode_basic(self):
        """单人模式正常分配"""
        ids = create_annotators(2)
        # 创建单人批次
        from app.models import QuestionBank, Question, Checkpoint, Video, EvalBatch
        db = TestSession()
        bank = QuestionBank(name="单人题库", version=1)
        db.add(bank)
        db.flush()
        for i in range(1, 6):
            q = Question(question_id=f"Q{i:04d}", bank_id=bank.id, prompt=f"p{i}")
            db.add(q)
            db.flush()
            db.add(Checkpoint(checkpoint_id=f"CP{i}-1", question_id=q.id, seq=1, text=f"cp{i}", min_success_line="x"))
        batch = EvalBatch(name="单人测试", bank_id=bank.id, model_version="v1", annotation_mode="single")
        db.add(batch)
        db.flush()
        for q in db.query(Question).filter(Question.bank_id == bank.id).all():
            db.add(Video(video_id=f"V{q.question_id[1:]}", batch_id=batch.id, question_id=q.id, oss_url=""))
        db.commit()
        batch_id = batch.id
        db.close()

        r = client.post(f"/api/batches/{batch_id}/assign-by-allocation", json={
            "allocations": [
                {"annotator_id": ids[0], "count": 3},
                {"annotator_id": ids[1], "count": 2},
            ],
            "annotation_mode": "single",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 5
        assert data["videos_assigned"] == 5
