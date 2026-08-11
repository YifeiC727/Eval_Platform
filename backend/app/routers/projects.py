from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectOut, UserCreate, UserOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=ProjectOut)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    existing = db.query(Project).filter(Project.project_id == data.project_id).first()
    if existing:
        raise HTTPException(400, "project_id already exists")
    p = Project(project_id=data.project_id, name=data.name, model_version=data.model_version)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    from app.models import Question, Video, Checkpoint, Assignment, Annotation, FinalResult

    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "project not found")

    questions = db.query(Question).filter(Question.project_id == project_id).all()
    q_ids = [q.id for q in questions]

    if q_ids:
        video_ids = [v.id for v in db.query(Video).filter(Video.question_id.in_(q_ids)).all()]
        cp_ids = [cp.id for cp in db.query(Checkpoint).filter(Checkpoint.question_id.in_(q_ids)).all()]

        if video_ids:
            assignment_ids = [a.id for a in db.query(Assignment).filter(Assignment.video_id.in_(video_ids)).all()]
            if assignment_ids:
                db.query(Annotation).filter(Annotation.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)
            db.query(Assignment).filter(Assignment.video_id.in_(video_ids)).delete(synchronize_session=False)
            db.query(FinalResult).filter(FinalResult.video_id.in_(video_ids)).delete(synchronize_session=False)
            db.query(Video).filter(Video.id.in_(video_ids)).delete(synchronize_session=False)

        if cp_ids:
            db.query(FinalResult).filter(FinalResult.checkpoint_id.in_(cp_ids)).delete(synchronize_session=False)
            db.query(Checkpoint).filter(Checkpoint.id.in_(cp_ids)).delete(synchronize_session=False)

        db.query(Question).filter(Question.id.in_(q_ids)).delete(synchronize_session=False)

    db.delete(p)
    db.commit()
    return {"status": "deleted", "project": p.name}


import hashlib

users_router = APIRouter(prefix="/api/users", tags=["users"])


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@users_router.post("/", response_model=UserOut)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(400, "username already exists")
    u = User(
        username=data.username,
        display_name=data.display_name,
        role=data.role,
        password_hash=_hash_password(data.password) if data.password else None,
        password_plain=data.password if data.password else None,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@users_router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@users_router.post("/login", response_model=UserOut)
def login(data: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(401, "用户不存在，请联系管理员创建账号")
    if user.password_hash and data.password:
        if _hash_password(data.password) != user.password_hash:
            raise HTTPException(401, "密码错误")
    elif user.password_hash and not data.password:
        raise HTTPException(401, "该账号需要密码，请输入密码")
    # No password_hash set → allow login without password
    user_roles = [r.strip() for r in user.role.split(",")]
    requested_role = data.role or user_roles[0]
    if requested_role not in user_roles:
        raise HTTPException(403, f"您没有 {requested_role} 权限，当前角色: {user.role}")
    return UserOut(id=user.id, username=user.username, display_name=user.display_name, role=requested_role)


@users_router.put("/{user_id}/password")
def set_password(user_id: int, data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "user not found")
    new_password = data.get("password")
    if not new_password or len(new_password) < 4:
        raise HTTPException(400, "密码至少4位")
    user.password_hash = _hash_password(new_password)
    user.password_plain = new_password
    db.commit()
    return {"status": "ok"}


@users_router.put("/{user_id}")
def update_user(user_id: int, data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "user not found")
    if "username" in data and data["username"]:
        existing = db.query(User).filter(User.username == data["username"], User.id != user_id).first()
        if existing:
            raise HTTPException(400, "用户名已存在")
        user.username = data["username"]
    if "display_name" in data:
        user.display_name = data["display_name"]
    if "role" in data and data["role"]:
        user.role = data["role"]
    db.commit()
    return {"status": "ok"}


@users_router.get("/{user_id}/password")
def get_password(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "user not found")
    return {"password": user.password_plain or "(未设置)"}


@users_router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    from app.models import Assignment, Annotation
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "user not found")
    # Delete related assignments and annotations
    assignment_ids = [a.id for a in db.query(Assignment).filter(Assignment.annotator_id == user_id).all()]
    if assignment_ids:
        db.query(Annotation).filter(Annotation.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)
    db.query(Assignment).filter(Assignment.annotator_id == user_id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    return {"status": "deleted", "username": user.username}


@users_router.post("/{user_id}/reset-tasks")
def reset_user_tasks(user_id: int, data: dict = {}, db: Session = Depends(get_db)):
    """重置某个标注员在某项目中的任务（删除其分配和标注，视频变回未分配）"""
    from app.models import Assignment, Annotation, FinalResult, Video, Question
    project_id = data.get("project_id")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "user not found")

    query = db.query(Assignment).filter(Assignment.annotator_id == user_id)
    if project_id:
        video_ids_in_project = [v.id for v in db.query(Video).join(Question).filter(Question.project_id == project_id).all()]
        query = query.filter(Assignment.video_id.in_(video_ids_in_project))

    assignments = query.all()
    deleted_assignments = 0
    deleted_annotations = 0
    deleted_finals = 0

    for a in assignments:
        # Delete annotations
        ann_count = db.query(Annotation).filter(Annotation.assignment_id == a.id).delete(synchronize_session=False)
        deleted_annotations += ann_count
        # Delete finals for this video+role (only if single mode or this was the only annotator)
        fr_count = db.query(FinalResult).filter(FinalResult.video_id == a.video_id).delete(synchronize_session=False)
        deleted_finals += fr_count
        db.delete(a)
        deleted_assignments += 1

    db.commit()
    return {
        "status": "reset",
        "username": user.display_name or user.username,
        "deleted_assignments": deleted_assignments,
        "deleted_annotations": deleted_annotations,
        "deleted_finals": deleted_finals,
    }
