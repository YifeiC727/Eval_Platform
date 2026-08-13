# 评测平台部署迁移指南

## 概述

开发机上已有旧版数据库，需要兼容升级到新版。本指南分两部分：
1. **Schema 迁移** — 在旧库上添加新列/新表
2. **30题测试数据导入** — 创建新的测试批次

---

## 新版功能清单

本次升级包含以下新功能：

| 功能 | 说明 |
|------|------|
| 项目成员管理 | 先把人加到批次，再从成员中分配任务 |
| 自动负载均衡分配 | 双人模式一键分配 A/B/C，按总任务数均衡 |
| 第三人仲裁完整流程 | 预分配→A/B提交→比对→C只看分歧→多数票/专家 |
| 技术无效处理链 | A/B/C均可报无效→自动沿链条降级→管理员兜底 |
| 失败码模式 | 批次创建时选 required/optional/disabled |
| 按批次提交锁定 | 标注员可分批次、分次提交已完成的题目 |
| 管理员待裁决入口 | 三人不一致/技术无效审核统一在"待我裁决" |
| 标注对比详情 | 管理员可查看 A/B/C/专家的完整标注对比 |
| Dashboard 批次筛选 | 能力排名/失败码/标签诊断按批次切换 |
| 导出修复 | 按 batch_id 正确过滤所有 sheet |
| T2AV 评测支持 | 支持文生音视频评测，48项能力(视频30+声音12+同步6) |
| 任务类型分组 | 批次区分 T2V/T2AV，看板按类型筛选 |
| T2AV 失败码 | 视频层用F01-F11，声音/同步层R用RF01-07、N用N1-N3 |
| 模块得分 | T2AV 展示 Visual/Audio/AV Sync/综合分 |
| sessionStorage 登录 | 多标签页不串号 |

---

## Part 1: Schema 迁移（兼容旧数据）

### 变更清单

| 变更 | 类型 | 说明 |
|------|------|------|
| `batch_members` 表 | 新增表 | 项目成员管理 |
| `eval_batches.fail_code_mode` | 新增列 | 失败码模式(required/optional/disabled) |
| `eval_batches.task_type` | 新增列 | 任务类型(t2v/t2av) |
| `questions.video_url` | 新增列 | 题目视频URL |
| `questions.project_id` | 新增列 | 项目ID（可能已存在） |

### 迁移脚本

在开发机后端目录执行：

```bash
cd backend
python3 migrate_to_new_version.py
```

此脚本（已在 `backend/migrate_to_new_version.py`）会：
1. 备份旧库
2. 创建 `batch_members` 表
3. 添加新列（已存在则跳过）
4. 修复旧失败码格式（F010→F10, F011→F11）
5. 从现有 assignments 自动生成 batch_members 记录

---

## Part 2: 导入30题测试数据

```bash
python3 import_30q_seed.py
```

此脚本（已在 `backend/import_30q_seed.py`）会：
1. 同步用户账号（不覆盖已有用户）
2. 创建"30题正式测试"题库（30题211检查点）
3. 创建"30题部署测试"批次
4. 幂等：重复执行不会重复导入

---

## Part 3: 技术无效处理逻辑

### 状态流转

```
标注员选"技术无效" → assignment.status = "issue_reported"
  ↓ 立即触发下游逻辑:
  - A报无效 + B正常 → 直接用B的答案定案
  - A/B都报无效 → C看全部检查点
  - C正常标注 → 用C的答案定案
  - C也报无效 → 分配expert给管理员
  
管理员操作:
  - "正常标注" → 管理员答案为最终结果
  - "确认技术无效(废弃)" → FinalResult.method="dropped", 不计入统计
```

### Case 矩阵

| A | B | C | 结果 |
|---|---|---|------|
| 正常 | 正常(一致) | - | consensus 定案 |
| 正常 | 正常(不一致) | 正常(多数) | majority 定案 |
| 正常 | 正常(不一致) | 正常(三人不同) | → 管理员裁决 |
| **无效** | 正常 | - | 直接用B定案(single) |
| 正常 | **无效** | - | 直接用A定案(single) |
| **无效** | **无效** | 正常 | 用C定案(single) |
| **无效** | **无效** | **无效** | → 管理员裁决(可drop) |
| 正常 | 正常(不一致) | **无效** | → 管理员裁决(可drop) |

### 关键约束

- `dropped` 的 FinalResult（score="X", method="dropped"）不参与任何统计
- `issue_reported` 的标注员已填数据保留在 DB 中但不参与比对
- 管理员 drop 后进度监控显示"已废弃"

---

## 文件清单

部署到开发机时需要的文件：

```
backend/
├── app/                          # 全部后端代码（覆盖旧版）
│   ├── models.py                 # +BatchMember, +fail_code_mode, +video_url
│   ├── routers/
│   │   ├── annotations.py       # 部分提交, expert处理, 技术无效链
│   │   ├── arbitration.py       # 批量分配仲裁人, 单个分配
│   │   ├── assignments.py       # third可见性, 级联重置, compare-view
│   │   ├── batches.py           # 成员管理, 负载均衡分配, fail_code_mode
│   │   ├── export.py            # batch_id过滤修复
│   │   ├── issues.py            # 技术无效上报+drop+下游触发
│   │   ├── scores.py            # batch_id过滤
│   │   └── ...
│   └── services/
│       ├── comparator.py        # 三人不一致→expert, both_invalid处理
│       └── scorer.py
├── data/
│   ├── deploy_30q_seed.json     # 30题种子数据
│   └── eval.db                  # 开发机旧库（原地迁移）
├── migrate_to_new_version.py    # Schema迁移脚本
├── import_30q_seed.py           # 30题数据导入脚本
└── requirements.txt

frontend/
├── src/views/
│   ├── Admin.vue                # 待裁决(不一致+技术无效), drop按钮
│   ├── Annotate.vue             # 失败码选择器, expert废弃按钮
│   ├── Dashboard.vue            # 批次筛选(abilities+failcodes+tags)
│   ├── TaskList.vue             # issue_reported在已完成tab, 部分提交
│   └── admin/
│       ├── BatchDetail.vue      # 成员管理, 一键分配, 详情弹窗, 仲裁状态
│       └── BatchList.vue        # fail_code_mode选项
└── vite.config.js               # proxy target=8000
```

---

## 增量部署（已部署过前版的情况）

如果线上已经跑着上一版（有 `fail_code_mode`、`batch_members` 等），只需：

```bash
# 1. 覆盖代码
# (git pull 或手动复制 backend/app/ 和 frontend/src/)

# 2. 数据库加 task_type 列（已存在则跳过）
cd backend
python3 migrate_to_new_version.py
# 或者手动执行:
# sqlite3 data/eval.db "ALTER TABLE eval_batches ADD COLUMN task_type TEXT DEFAULT 't2v';"

# 3. 重启后端
pkill -f uvicorn; sleep 1
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 4. 前端重新构建
cd ../frontend
npm run build
# 或开发模式: npm run dev

# 5. 验证
curl http://localhost:8000/api/batches/ | python3 -c "import json,sys; [print(b['name'], b.get('task_type')) for b in json.load(sys.stdin)[:3]]"
```

本次新增内容：
- `eval_batches.task_type` 列（默认 `t2v`，可选 `t2av`）
- T2AV 失败码验证支持（RF01-RF07, N1-N3）
- 看板按任务类型筛选
- 模块得分 API (`/api/scores/modules`)
- 标注界面按检查点层级展示失败码
- sessionStorage 替代 localStorage（多标签页不串号）

已有数据完全兼容，旧批次自动为 `task_type=t2v`。

---

## 首次完整部署

```bash
# 1. 覆盖代码
# (git pull 或手动复制 backend/app/ 和 frontend/src/)

# 2. 安装依赖
cd backend && pip install -r requirements.txt

# 3. 数据库迁移（安全，只做ADD）
python3 migrate_to_new_version.py

# 4. 导入30题测试数据（幂等）
python3 import_30q_seed.py

# 5. 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 6. 前端
cd ../frontend
npm install
npm run build
# 生产用 nginx 托管 dist/ 并反代 /api → localhost:8000
# 开发用: npm run dev

# 7. 验证
curl http://localhost:8000/api/batches/
curl http://localhost:8000/api/scores/abilities
```

---

## 注意事项

1. **不删除旧数据** — 迁移脚本只做 ADD
2. **vite proxy** — `frontend/vite.config.js` 中 target 指向后端端口（默认8000）
3. **管理员** — 陈逸菲 / `123456`
4. **标注员** — ann_01~ann_21，密码格式 `eval{NN}@2026`
5. **fail_code_mode** — 旧批次自动设为 `optional`
6. **视频URL为空** — 通过管理后台 BatchDetail → 更新URL 接口补充
7. **技术无效** — `/issues/report` 会立即触发下游逻辑（不需要额外 submit）
8. **级联删除** — 重置 A/B 会级联删除 third/expert + FinalResult
