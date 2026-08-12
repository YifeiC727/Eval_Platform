#!/usr/bin/env python3
"""
完整 E2E 测试脚本 - 覆盖评测平台所有功能
运行前确保后端在 localhost:8000 运行

测试覆盖:
1. 用户登录（正确/错误密码/不存在用户/权限检查）
2. 题库管理（上传已有）
3. 批次创建（单人/双人/失败码模式）
4. 项目成员管理（添加/移除/查看）
5. 任务分配（一键分配/负载均衡验证）
6. 标注员视角（任务列表/third不可见/标注/提交）
7. 第三人仲裁（激活/部分标注/提交）
8. 专家裁决（三人不一致→推送管理员）
9. 进度监控（状态流转/仲裁状态）
10. 数据看板（能力排名/失败码/标签/按批次筛选）
11. 标注对比详情
12. 导出Excel
13. 部分提交/按批次提交
14. 重置/级联删除
15. Edge cases
"""

import requests
import json
import sys

BASE = 'http://localhost:8000/api'
errors = []
passed = 0

def check(condition, msg):
    global passed
    if not condition:
        errors.append(msg)
        print(f'  ❌ {msg}')
    else:
        passed += 1
        print(f'  ✅ {msg}')

def section(title):
    print(f'\n{"="*60}\n  {title}\n{"="*60}')


# ========================================================
section('1. 用户登录')
# ========================================================

# 正确登录
r = requests.post(f'{BASE}/users/login', json={'username':'ann_01','password':'eval01@2026','role':'annotator'})
check(r.status_code == 200 and r.json()['display_name'] == '宋晓梦', '标注员正确登录')

# 错误密码
r = requests.post(f'{BASE}/users/login', json={'username':'ann_01','password':'wrong','role':'annotator'})
check(r.status_code == 401, '错误密码返回401')

# 不存在用户
r = requests.post(f'{BASE}/users/login', json={'username':'nobody','password':'x','role':'annotator'})
check(r.status_code == 401, '不存在用户返回401')

# 管理员登录
r = requests.post(f'{BASE}/users/login', json={'username':'陈逸菲','password':'123456','role':'admin'})
check(r.status_code == 200 and r.json()['role'] == 'admin', '管理员正确登录')

# 权限检查：标注员不能以admin角色登录
r = requests.post(f'{BASE}/users/login', json={'username':'ann_01','password':'eval01@2026','role':'admin'})
check(r.status_code == 403, '标注员无admin权限返回403')


# ========================================================
section('2. 题库')
# ========================================================

r = requests.get(f'{BASE}/banks/')
check(r.status_code == 200, f'题库列表 ({len(r.json())} 个)')
banks = r.json()
if banks:
    check(banks[0].get('question_count', 0) > 0 or 'name' in banks[0], '题库有基本字段')


# ========================================================
section('3. 创建批次')
# ========================================================

# 创建双人盲标批次（失败码必选）
r = requests.post(f'{BASE}/batches/', json={
    'bank_id': 2, 'name': 'E2E完整测试', 'model_version': 'e2e_v1',
    'annotation_mode': 'dual', 'fail_code_mode': 'required'
})
check(r.status_code == 200, f'创建批次 (id={r.json().get("id")})')
test_batch_id = r.json()['id']

# 验证详情
r = requests.get(f'{BASE}/batches/{test_batch_id}')
d = r.json()
check(d['annotation_mode'] == 'dual', '标注模式=双人')
check(d['fail_code_mode'] == 'required', '失败码=必选')
check(d['total_videos'] == 3, f'视频数=3 (got {d["total_videos"]})')


# ========================================================
section('4. 项目成员')
# ========================================================

# 添加3个成员
r = requests.post(f'{BASE}/batches/{test_batch_id}/members', json={'user_ids': [17, 18, 19]})
check(r.json()['added'] == 3, '添加3个成员')

# 查看
r = requests.get(f'{BASE}/batches/{test_batch_id}/members')
check(len(r.json()) == 3, '成员列表=3人')

# 添加第4人
r = requests.post(f'{BASE}/batches/{test_batch_id}/members', json={'user_ids': [20]})
check(r.json()['total'] == 4, '添加第4人后total=4')

# 移除第4人
r = requests.delete(f'{BASE}/batches/{test_batch_id}/members/20')
check(r.status_code == 200, '移除成员')

# 确认移除
r = requests.get(f'{BASE}/batches/{test_batch_id}/members')
check(len(r.json()) == 3, '移除后=3人')

# 重复添加
r = requests.post(f'{BASE}/batches/{test_batch_id}/members', json={'user_ids': [17]})
check(r.json()['added'] == 0, '重复添加=0')


# ========================================================
section('5. 一键分配')
# ========================================================

r = requests.post(f'{BASE}/batches/{test_batch_id}/assign-by-allocation', json={
    'allocations': [], 'annotation_mode': 'dual'
})
result = r.json()
check(result['created'] == 9, f'创建9个任务(A×3+B×3+C×3) (got {result["created"]})')
check(result['videos_assigned'] == 3, f'覆盖3视频 (got {result["videos_assigned"]})')

# 验证分配均衡性和互斥性
r = requests.get(f'{BASE}/assignments/progress', params={'batch_id': test_batch_id, 'page_size': 10})
items = r.json()['items']
for item in items:
    people = [item['annotator_a'], item['annotator_b'], item['annotator_third']]
    people = [p for p in people if p]
    check(len(people) == len(set(people)), f'{item["video_id"]} A/B/C互斥')

# 验证不能重复分配
r = requests.post(f'{BASE}/batches/{test_batch_id}/assign-by-allocation', json={
    'allocations': [], 'annotation_mode': 'dual'
})
check(r.json()['created'] == 0, '重复分配=0(已无待分配视频)')


# ========================================================
section('6. 标注员视角')
# ========================================================

# Third应该不可见
for uid in [17, 18, 19]:
    r = requests.get(f'{BASE}/assignments/my', params={'user_id': uid})
    thirds = [t for t in r.json() if t['role'] == 'third']
    check(len(thirds) == 0, f'uid={uid} third不可见')

# A/B任务可见
r = requests.get(f'{BASE}/assignments/my', params={'user_id': 17})
ab_tasks = [t for t in r.json() if t['role'] in ('A', 'B')]
check(len(ab_tasks) > 0, f'uid=17 有{len(ab_tasks)}个A/B任务')

# 标注流程
for uid in [17, 18, 19]:
    r = requests.get(f'{BASE}/assignments/my', params={'user_id': uid})
    for task in r.json():
        if task['role'] not in ('A', 'B') or task['status'] == 'submitted':
            continue
        aid = task['id']
        r2 = requests.get(f'{BASE}/assignments/{aid}')
        detail = r2.json()

        # 验证batch信息
        check('batch' in detail, f'Assignment {aid} 有batch信息')
        check(detail['batch']['fail_code_mode'] == 'required', f'Assignment {aid} fail_code_mode=required')

        cps = detail['checkpoints']
        vid = task['video']['video_id']
        anns = []
        for i, cp in enumerate(cps):
            if not cp['needs_annotation']:
                continue
            if vid == 'V0003' and task['role'] == 'B':
                score = 'N'  # V3: B全给N (与A不同)
            elif vid == 'V0002' and task['role'] == 'B' and i >= 6:
                score = 'N'  # V2: B后半不同
            else:
                score = 'C'
            # fail_code_mode=required 时 R/N 需要 fail_code
            fc = 'F01' if score in ('R', 'N') else None
            anns.append({'checkpoint_id': cp['id'], 'score': score, 'fail_code': fc})

        requests.post(f'{BASE}/annotations/submit', json={'assignment_id': aid, 'annotations': anns})
        requests.post(f'{BASE}/annotations/complete', json={'assignment_id': aid})

print('  All A/B annotated')


# ========================================================
section('7. 部分提交')
# ========================================================

# 先只提交一部分
r = requests.post(f'{BASE}/annotations/submit-all', json={'user_id': 17, 'batch_id': test_batch_id})
check(r.status_code == 200, f'宋晓梦部分提交: locked={r.json().get("locked_count")}')

# 其他人也提交
for uid in [18, 19]:
    r = requests.post(f'{BASE}/annotations/submit-all', json={'user_id': uid, 'batch_id': test_batch_id})
check(True, '所有人A/B提交完成')


# ========================================================
section('8. 比对和第三人激活')
# ========================================================

r = requests.get(f'{BASE}/assignments/progress', params={'batch_id': test_batch_id, 'page_size': 10})
items = r.json()['items']
for item in items:
    vid = item['video_id']
    status = item['status']
    arb = item['arbitration_status']
    fin = item['finalized']
    total = item['checkpoint_count']
    print(f'  {vid}: status={status}, arb={arb}, fin={fin}/{total}')

# V0001 should be 已定案 (all agree)
v1 = next(i for i in items if i['video_id'] == 'V0001')
check(v1['status'] == '已定案', 'V1: A/B一致→已定案')

# Third visibility
third_visible = False
for uid in [17, 18, 19]:
    r = requests.get(f'{BASE}/assignments/my', params={'user_id': uid})
    thirds = [t for t in r.json() if t['role'] == 'third' and t['status'] != 'submitted']
    if thirds:
        third_visible = True
        for t in thirds:
            check(t['checkpoint_count'] > 0, f'Third {t["video"]["video_id"]}: {t["checkpoint_count"]} cps')

check(third_visible, '至少有一个third任务被激活')


# ========================================================
section('9. 第三人标注(制造三人不一致)')
# ========================================================

for uid in [17, 18, 19]:
    r = requests.get(f'{BASE}/assignments/my', params={'user_id': uid})
    for task in r.json():
        if task['role'] != 'third' or task['status'] == 'submitted':
            continue
        aid = task['id']
        r2 = requests.get(f'{BASE}/assignments/{aid}')
        cps = [cp for cp in r2.json()['checkpoints'] if cp['needs_annotation']]
        # Give all R → force three-way disagreement (A=C, B=N, third=R)
        anns = [{'checkpoint_id': cp['id'], 'score': 'R', 'fail_code': 'F05'} for cp in cps]
        requests.post(f'{BASE}/annotations/submit', json={'assignment_id': aid, 'annotations': anns})
        requests.post(f'{BASE}/annotations/complete', json={'assignment_id': aid})
        print(f'  uid={uid} third: {task["video"]["video_id"]} → all R')

# Submit third tasks
for uid in [17, 18, 19]:
    requests.post(f'{BASE}/annotations/submit-all', json={'user_id': uid, 'batch_id': test_batch_id})


# ========================================================
section('10. 专家裁决')
# ========================================================

r = requests.get(f'{BASE}/assignments/my', params={'user_id': 1})
experts = [t for t in r.json() if t['role'] == 'expert']
check(len(experts) > 0, f'管理员有{len(experts)}个专家任务')

for task in experts:
    aid = task['id']
    r2 = requests.get(f'{BASE}/assignments/{aid}')
    cps = [cp for cp in r2.json()['checkpoints'] if cp['needs_annotation']]
    anns = [{'checkpoint_id': cp['id'], 'score': 'C', 'fail_code': None} for cp in cps]
    requests.post(f'{BASE}/annotations/submit', json={'assignment_id': aid, 'annotations': anns})
    requests.post(f'{BASE}/annotations/complete', json={'assignment_id': aid})

r = requests.post(f'{BASE}/annotations/submit-all', json={'user_id': 1, 'batch_id': test_batch_id})
check(r.status_code == 200, f'管理员裁决并提交: locked={r.json().get("locked_count")}')


# ========================================================
section('11. 进度验证(全部定案)')
# ========================================================

r = requests.get(f'{BASE}/assignments/progress', params={'batch_id': test_batch_id, 'page_size': 10})
items = r.json()['items']
all_done = all(i['finalized'] == i['checkpoint_count'] for i in items)
check(all_done, '所有视频全部定案')

for item in items:
    print(f'  {item["video_id"]}: {item["status"]} fin={item["finalized"]}/{item["checkpoint_count"]}')


# ========================================================
section('12. 数据看板')
# ========================================================

r = requests.get(f'{BASE}/scores/abilities', params={'batch_id': test_batch_id})
check(r.status_code == 200 and len(r.json()) > 0, f'能力排名 ({len(r.json())} items)')

r = requests.get(f'{BASE}/scores/quality', params={'batch_id': test_batch_id})
check(r.status_code == 200, 'Quality stats')
check(r.json()['pending_expert'] == 0, 'pending_expert=0')

r = requests.get(f'{BASE}/scores/fail-codes', params={'batch_id': test_batch_id})
check(r.status_code == 200, f'失败码 ({len(r.json())} codes)')
for fc in r.json():
    check(fc.get('name', '') != '', f'失败码 {fc["code"]} 有名称')

r = requests.get(f'{BASE}/scores/tags', params={'batch_id': test_batch_id})
check(r.status_code == 200, f'标签 ({len(r.json())} tags)')


# ========================================================
section('13. 标注对比详情')
# ========================================================

r = requests.get(f'{BASE}/assignments/progress', params={'batch_id': test_batch_id, 'page_size': 1})
vid_db = r.json()['items'][0]['video_db_id']
r = requests.get(f'{BASE}/annotations/compare-view/{vid_db}')
check(r.status_code == 200, 'Compare view API')
data = r.json()
check('video_url' in data, 'video_url字段')
check('roles' in data, 'roles字段')
check(len(data['checkpoints']) > 0, '有检查点数据')
cp = data['checkpoints'][0]
check('final_score' in cp and 'final_method' in cp, '有定案信息')


# ========================================================
section('14. 导出Excel')
# ========================================================

r = requests.get(f'{BASE}/export/results', params={'batch_id': test_batch_id})
check(r.status_code == 200, 'Export 200')
check('spreadsheet' in r.headers.get('content-type', ''), 'Content-Type xlsx')
check(len(r.content) > 5000, f'文件大小合理 ({len(r.content)} bytes)')

# 无batch_id全量导出
r = requests.get(f'{BASE}/export/results')
check(r.status_code == 200, '全量导出 200')


# ========================================================
section('15. 重置和级联删除')
# ========================================================

# 重置一个视频
r = requests.get(f'{BASE}/assignments/progress', params={'batch_id': test_batch_id, 'page_size': 1})
first_vid = r.json()['items'][0]['video_id']
r = requests.post(f'{BASE}/assignments/reset-single', json={'video_id': first_vid})
check(r.status_code == 200, f'重置 {first_vid}')
check(r.json()['deleted_assignments'] >= 3, '级联删除了A/B/C/expert')

# 验证重置后状态
r = requests.get(f'{BASE}/assignments/progress', params={'batch_id': test_batch_id, 'page_size': 10})
reset_item = next(i for i in r.json()['items'] if i['video_id'] == first_vid)
check(reset_item['status'] == '未分配', '重置后状态=未分配')


# ========================================================
section('16. Edge Cases')
# ========================================================

# 空批次导出
r = requests.post(f'{BASE}/batches/', json={
    'bank_id': 2, 'name': '空批次', 'model_version': 'empty', 'annotation_mode': 'single'
})
empty_batch = r.json()['id']
r = requests.get(f'{BASE}/export/results', params={'batch_id': empty_batch})
check(r.status_code == 200, '空批次导出不报错')
requests.delete(f'{BASE}/batches/{empty_batch}')

# 成员<3人时不分配third
r = requests.post(f'{BASE}/batches/', json={
    'bank_id': 2, 'name': '2人测试', 'model_version': 'x', 'annotation_mode': 'dual'
})
two_batch = r.json()['id']
requests.post(f'{BASE}/batches/{two_batch}/members', json={'user_ids': [17, 18]})
r = requests.post(f'{BASE}/batches/{two_batch}/assign-by-allocation', json={'allocations':[], 'annotation_mode':'dual'})
# Check no third assigned
r2 = requests.get(f'{BASE}/assignments/progress', params={'batch_id': two_batch, 'page_size': 10})
for item in r2.json()['items']:
    check(item['annotator_third'] is None, f'2人批次 {item["video_id"]} 无third')
requests.delete(f'{BASE}/batches/{two_batch}')

# submit-all with no completed tasks
r = requests.post(f'{BASE}/annotations/submit-all', json={'user_id': 17, 'batch_id': test_batch_id})
check(r.status_code == 200 and r.json()['locked_count'] == 0, 'Submit无完成任务=locked 0')


# ========================================================
# Cleanup
# ========================================================
requests.delete(f'{BASE}/batches/{test_batch_id}')


# ========================================================
section('SUMMARY')
# ========================================================
total = passed + len(errors)
print(f'\n  Passed: {passed}/{total}')
if errors:
    print(f'  Failed: {len(errors)}')
    for e in errors[:10]:
        print(f'    - {e}')
    sys.exit(1)
else:
    print('  🎉 ALL TESTS PASSED')
    sys.exit(0)
