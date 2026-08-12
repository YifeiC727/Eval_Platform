#!/usr/bin/env python3
"""
数据库 Schema 迁移脚本
将旧版数据库升级到新版（含仲裁流程+失败码模式+成员管理）
可重复执行，已存在的结构会跳过
"""
import sqlite3
import shutil
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'eval.db')

if not os.path.exists(DB_PATH):
    print(f'❌ 数据库不存在: {DB_PATH}')
    exit(1)

# 1. 备份
backup = f'{DB_PATH}.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
shutil.copy2(DB_PATH, backup)
print(f'[1/5] 备份完成: {backup}')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 2. 新表
print('[2/5] 创建新表...')
cur.execute('''CREATE TABLE IF NOT EXISTS batch_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES eval_batches(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    added_at TEXT,
    UNIQUE(batch_id, user_id)
)''')
print('  batch_members ✓')

# 3. 新列
print('[3/5] 添加新列...')
alter_cmds = [
    ('eval_batches', 'fail_code_mode', 'TEXT DEFAULT "optional"'),
    ('questions', 'video_url', 'TEXT'),
    ('questions', 'project_id', 'INTEGER'),
]
for table, col, col_type in alter_cmds:
    try:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
        print(f'  {table}.{col} ✓')
    except sqlite3.OperationalError:
        print(f'  {table}.{col} (已存在，跳过)')

# 4. 数据修复
print('[4/5] 数据修复...')
n1 = cur.execute("UPDATE annotations SET fail_code='F10' WHERE fail_code='F010'").rowcount
n2 = cur.execute("UPDATE annotations SET fail_code='F11' WHERE fail_code='F011'").rowcount
n3 = cur.execute("UPDATE final_results SET final_fail_code='F10' WHERE final_fail_code='F010'").rowcount
n4 = cur.execute("UPDATE final_results SET final_fail_code='F11' WHERE final_fail_code='F011'").rowcount
print(f'  失败码修复: annotations={n1+n2}, final_results={n3+n4}')

# 5. 从现有 assignments 自动生成 batch_members
print('[5/5] 生成 batch_members...')
cur.execute('''
INSERT OR IGNORE INTO batch_members (batch_id, user_id, added_at)
SELECT DISTINCT v.batch_id, a.annotator_id, datetime('now')
FROM assignments a
JOIN videos v ON a.video_id = v.id
WHERE v.batch_id IS NOT NULL
''')
print(f'  生成 {cur.rowcount} 条成员记录')

conn.commit()
conn.close()
print('\n✅ 迁移完成')
