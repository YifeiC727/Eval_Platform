"""
数据迁移脚本: 旧 Project 结构 → 新 QuestionBank + EvalBatch 结构

运行方式: cd backend && python migrate_to_v2.py

逻辑:
1. 为每个旧 Project 创建一个 QuestionBank
2. 将 Question 的 project_id 改为 bank_id
3. 为每个旧 Project 创建一个 EvalBatch
4. 将 Video 的 question_id 关联改为 batch_id + question_id

注意: 运行前请备份 eval.db！
"""
import sys
import os
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, SessionLocal
from sqlalchemy import text, inspect


def migrate():
    db = SessionLocal()

    # Check if new tables exist
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "question_banks" not in existing_tables:
        print("Creating new tables...")
        from app.models import Base
        Base.metadata.create_all(bind=engine)
        print("  Tables created.")

    # Check if there's data to migrate
    with engine.connect() as conn:
        projects = conn.execute(text("SELECT * FROM projects")).fetchall()
        if not projects:
            print("No projects to migrate.")
            return

    print(f"Found {len(projects)} projects to migrate.")

    # Add bank_id column to questions if not exists
    with engine.connect() as conn:
        cols = [c["name"] for c in inspector.get_columns("questions")]
        if "bank_id" not in cols:
            conn.execute(text("ALTER TABLE questions ADD COLUMN bank_id INTEGER"))
            conn.commit()
            print("  Added bank_id to questions table")

        # Add batch_id column to videos if not exists
        cols = [c["name"] for c in inspector.get_columns("videos")]
        if "batch_id" not in cols:
            conn.execute(text("ALTER TABLE videos ADD COLUMN batch_id INTEGER"))
            conn.commit()
            print("  Added batch_id to videos table")

    for project in projects:
        p_id = project[0]  # id
        p_project_id = project[1]  # project_id
        p_name = project[2]  # name
        p_model_version = project[3]  # model_version
        p_created_at = project[5]  # created_at

        print(f"\nMigrating project: {p_name} (id={p_id})")

        # 1. Create QuestionBank
        with engine.connect() as conn:
            # Check if already migrated
            existing_bank = conn.execute(
                text("SELECT id FROM question_banks WHERE name = :name"),
                {"name": p_name}
            ).fetchone()

            if existing_bank:
                bank_id = existing_bank[0]
                print(f"  Bank already exists: id={bank_id}")
            else:
                conn.execute(text(
                    "INSERT INTO question_banks (name, version, description, created_at, updated_at) VALUES (:name, 1, :desc, :created, :updated)"
                ), {"name": p_name, "desc": f"从项目 {p_project_id} 迁移", "created": p_created_at, "updated": datetime.utcnow().isoformat()})
                conn.commit()
                bank_id = conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]
                print(f"  Created bank: id={bank_id}")

            # 2. Update questions to reference bank
            conn.execute(text(
                "UPDATE questions SET bank_id = :bank_id WHERE project_id = :project_id"
            ), {"bank_id": bank_id, "project_id": p_id})
            conn.commit()

            q_count = conn.execute(text(
                "SELECT COUNT(*) FROM questions WHERE bank_id = :bank_id"
            ), {"bank_id": bank_id}).fetchone()[0]
            print(f"  Linked {q_count} questions to bank")

            # 3. Create EvalBatch
            existing_batch = conn.execute(
                text("SELECT id FROM eval_batches WHERE bank_id = :bank_id AND model_version = :mv"),
                {"bank_id": bank_id, "mv": p_model_version or ""}
            ).fetchone()

            if existing_batch:
                batch_id = existing_batch[0]
                print(f"  Batch already exists: id={batch_id}")
            else:
                conn.execute(text(
                    "INSERT INTO eval_batches (name, bank_id, model_version, annotation_mode, status, created_at) VALUES (:name, :bank_id, :mv, 'single', 'labeling', :created)"
                ), {"name": f"{p_name} - {p_model_version or 'v1'}", "bank_id": bank_id, "mv": p_model_version or "", "created": p_created_at})
                conn.commit()
                batch_id = conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]
                print(f"  Created batch: id={batch_id}")

            # 4. Update videos to reference batch
            # Videos are linked via question_id, we just need to set batch_id
            conn.execute(text("""
                UPDATE videos SET batch_id = :batch_id
                WHERE question_id IN (SELECT id FROM questions WHERE bank_id = :bank_id)
            """), {"batch_id": batch_id, "bank_id": bank_id})
            conn.commit()

            v_count = conn.execute(text(
                "SELECT COUNT(*) FROM videos WHERE batch_id = :batch_id"
            ), {"batch_id": batch_id}).fetchone()[0]
            print(f"  Linked {v_count} videos to batch")

    print("\n✅ Migration complete!")
    print("  Old 'projects' table is preserved but no longer used by new code.")
    print("  You can verify by visiting the admin panel.")

    db.close()


if __name__ == "__main__":
    # Backup first
    db_path = os.path.join(os.path.dirname(__file__), "data", "eval.db")
    if os.path.exists(db_path):
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(db_path, backup_path)
        print(f"Backed up database to: {backup_path}")

    migrate()
