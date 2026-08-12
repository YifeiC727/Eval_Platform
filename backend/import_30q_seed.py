#!/usr/bin/env python3
"""
导入30题测试数据集
从 deploy_30q_seed.json 导入题库+题目+检查点+用户
不影响数据库中已有的数据
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'eval.db')
SEED_PATH = os.path.join(os.path.dirname(__file__), 'data', 'deploy_30q_seed.json')

if not os.path.exists(DB_PATH):
    print(f'❌ 数据库不存在: {DB_PATH}')
    exit(1)
if not os.path.exists(SEED_PATH):
    print(f'❌ 种子文件不存在: {SEED_PATH}')
    exit(1)

with open(SEED_PATH, 'r', encoding='utf-8') as f:
    seed = json.load(f)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
now = datetime.utcnow().isoformat()

# 1. 同步用户
print('[1/5] 同步用户...')
new_users = 0
for user in seed['users']:
    existing = cur.execute('SELECT id FROM users WHERE username=?', (user['username'],)).fetchone()
    if not existing:
        cur.execute('''INSERT INTO users (username, password_hash, password_plain, display_name, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (user['username'], user.get('password_hash'), user.get('password_plain'),
             user['display_name'], user['role'], now))
        new_users += 1
print(f'  新增 {new_users} / 已有 {len(seed["users"])-new_users}')

# 2. 检查是否已导入过
bank_name = seed['question_banks'][0]['name']
existing_bank = cur.execute('SELECT id FROM question_banks WHERE name=?', (bank_name,)).fetchone()
if existing_bank:
    print(f'\n⚠️ 题库 "{bank_name}" 已存在 (id={existing_bank[0]})，跳过数据导入')
    conn.commit()
    conn.close()
    print('✅ 用户同步完成，题库已存在无需重复导入')
    exit(0)

# 3. 创建题库
print('[2/5] 创建题库...')
bank = seed['question_banks'][0]
cur.execute('INSERT INTO question_banks (name, version, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
    (bank['name'], bank['version'], bank.get('description', ''), now, now))
new_bank_id = cur.lastrowid
print(f'  "{bank["name"]}" → id={new_bank_id}')

# 4. 导入题目
print('[3/5] 导入题目...')
old_to_new_q = {}
for q in seed['questions']:
    cur.execute('''INSERT INTO questions (question_id, bank_id, prompt, language, preprocess_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)''',
        (q['question_id'], new_bank_id, q['prompt'], q.get('language'), q.get('preprocess_note'), now))
    old_to_new_q[q['id']] = cur.lastrowid
print(f'  {len(seed["questions"])} 题')

# 5. 导入检查点
print('[4/5] 导入检查点...')
cp_count = 0
for cp in seed['checkpoints']:
    new_qid = old_to_new_q.get(cp['question_id'])
    if not new_qid:
        continue
    cur.execute('''INSERT INTO checkpoints (checkpoint_id, question_id, seq, text, min_success_line,
        ability_id, ability_name, tag_id, tag_name, evidence_period, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (cp['checkpoint_id'], new_qid, cp.get('seq'), cp['text'], cp.get('min_success_line'),
         cp.get('ability_id'), cp.get('ability_name'), cp.get('tag_id'), cp.get('tag_name'),
         cp.get('evidence_period'), now))
    cp_count += 1
print(f'  {cp_count} 检查点')

# 6. 创建批次
print('[5/5] 创建测试批次...')
cur.execute('''INSERT INTO eval_batches (name, bank_id, model_version, annotation_mode, fail_code_mode, status, description, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
    ('30题部署测试', new_bank_id, 'deploy_v1', 'dual', 'optional', 'preparing',
     '30题测试集，用于部署验证', now))
batch_id = cur.lastrowid

# 创建 videos
for old_qid, new_qid in old_to_new_q.items():
    q_id_str = cur.execute('SELECT question_id FROM questions WHERE id=?', (new_qid,)).fetchone()[0]
    seq = q_id_str.replace('Q', '')
    cur.execute('INSERT INTO videos (video_id, batch_id, question_id, oss_url, status, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        (f'V{seq}', batch_id, new_qid, '', 'active', now))
print(f'  批次 "{batch_id}" → 30 videos')

conn.commit()
conn.close()

print(f'''
✅ 导入完成

题库: "{bank_name}" (id={new_bank_id})
批次: "30题部署测试" (id={batch_id})
题目: 30题, {cp_count} 检查点

下一步:
  1. 启动后端: uvicorn app.main:app --port 8000
  2. 管理员登录（陈逸菲 / 123456）
  3. 评测批次 → "30题部署测试" → 添加成员 → 一键分配
''')
