# V6 T2V 评测平台

视频生成模型（T2V）标注评测平台，支持多人协作标注、自动比对仲裁、能力得分计算。

## 快速部署

### 环境要求

- Python 3.10+
- Node.js 18+
- pip, npm

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

首次启动会自动创建 SQLite 数据库文件 `backend/data/eval.db`。

### 2. 前端

```bash
cd frontend
npm install
npm run dev -- --port 5173 --host 0.0.0.0
```

前端默认代理 `/api` 到后端 `http://localhost:8001`，如果后端端口不同需修改 `frontend/vite.config.js`。

### 3. 生产部署（可选）

```bash
# 前端构建
cd frontend && npm run build

# 用 nginx 或让 FastAPI 托管 dist 目录
# 后端用 gunicorn 启动
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

---

## 首次使用流程

### 第一步：创建管理员账号

```bash
curl -X POST http://localhost:8001/api/users/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "display_name": "管理员", "role": "admin", "password": "your_password"}'
```

或者在代码中直接运行：

```python
import hashlib
from app.database import SessionLocal
from app.models import User

db = SessionLocal()
db.add(User(
    username="admin",
    display_name="管理员",
    role="admin",
    password_hash=hashlib.sha256("your_password".encode()).hexdigest(),
    password_plain="your_password",
))
db.commit()
```

### 第二步：管理员登录，创建标注员

登录后进入管理后台 → 标注员 → 添加标注员（设置用户名和密码）。

### 第三步：新建项目，导入数据

管理后台 → 数据导入 → 新建项目 → 上传检查点拆解 Excel。

Excel 文件要求两个 sheet：
- **原题** — 列：题目ID, 原序号, 原Prompt（保留原文）, 语言, 预处理说明
- **检查点拆解** — 列：题目ID, 检查点ID, 原子检查点, 核心能力ID, 核心能力名称, 三级标签ID, 三级标签名称, 最低成功线, 证据时段（如有）, 预处理说明

导入后系统自动为每道题创建视频占位记录。

### 第四步：配置视频 URL

通过 API 批量更新视频 URL：

```python
import csv
from app.database import SessionLocal
from app.models import Video, Question

db = SessionLocal()
with open("videos.csv") as f:
    for row in csv.DictReader(f):
        q = db.query(Question).filter(Question.question_id == row["题目ID"]).first()
        if q:
            v = db.query(Video).filter(Video.question_id == q.id).first()
            if v:
                v.oss_url = row["视频URL"]
db.commit()
```

### 第五步：分配任务

管理后台 → 任务分配 → 选择项目、标注员、标注模式（单人/双人）→ 执行分配。

### 第六步：标注员标注

标注员用分配的用户名登录 → 看到任务列表 → 逐题标注 C/R/N/NA → 全部完成后点"全部提交锁定"。

### 第七步：导出结果

管理后台 → 导出结果 → 下载 Excel（含能力得分、标注员统计、题目明细等 7 个 sheet）。

---

## 数据库结构

SQLite 文件位于 `backend/data/eval.db`，包含以下表：

| 表 | 说明 |
|----|------|
| users | 用户（标注员/组长/管理员） |
| projects | 评测项目 |
| questions | 题目（Prompt） |
| videos | 视频（OSS URL） |
| checkpoints | 原子检查点（绑定能力和标签） |
| assignments | 任务分配（视频×标注员×角色） |
| annotations | 标注记录（C/R/N/NA） |
| final_results | 定案结果 |

---

## API 文档

启动后端后访问 `http://localhost:8001/docs` 查看自动生成的 OpenAPI 文档。

主要接口：

| 接口 | 说明 |
|------|------|
| POST /api/users/login | 登录 |
| POST /api/import/checkpoints | 导入 Excel |
| POST /api/assignments/assign | 分配任务 |
| POST /api/annotations/submit | 保存标注 |
| POST /api/annotations/submit-all | 全部提交锁定 |
| GET /api/scores/abilities | 30 项能力得分 |
| GET /api/stats/overview | 项目总览统计 |
| GET /api/export/results | 导出 Excel |

---

## 计分公式

- C = 1.0, R = 0.3, N = 0.0, NA = 不计入
- 能力得分: `AbilityScore(c) = Σ(该能力检查点分值) / n(c) × 100`
- 题目完成率: `Score(q) = Σ(检查点分值) / K × 100`
- 覆盖状态: n≥10 正式排名 / 5≤n<10 初步趋势 / n<5 证据不足

---

## 目录结构

```
评测平台/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── models.py         # 数据库模型
│   │   ├── database.py       # DB 配置
│   │   ├── schemas.py        # 请求/响应模型
│   │   ├── routers/          # API 路由
│   │   └── services/         # 业务逻辑
│   ├── data/                  # SQLite 数据库
│   ├── tests/                 # 测试用例
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/            # 页面组件
│   │   ├── App.vue           # 主布局
│   │   ├── router.js         # 路由
│   │   └── api.js            # 接口封装
│   ├── vite.config.js
│   └── package.json
└── README.md
```

---

## 登录说明

- 管理员创建用户时可设置密码，也可不设
- 设了密码的账号：登录时必须输入密码
- 没设密码的账号：用户名即可登录
- 一个用户可有多角色（如 `admin,annotator`），登录时选择身份

---

## 注意事项

1. SQLite 适合 20 人以下并发。如需更高并发，改 `backend/app/database.py` 中的 `DATABASE_URL` 为 MySQL/PostgreSQL
2. 视频通过 OSS 签名 URL 播放，确保部署机器能访问视频存储
3. 数据库文件 `eval.db` 是所有数据的唯一存储，务必定期备份
4. 前端开发模式用 Vite 热更新，生产环境需 `npm run build` 后用 nginx 托管
