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
    if not user.password_hash:
        raise HTTPException(401, "账号未设置密码，请联系管理员设置")
    if not data.password:
        raise HTTPException(401, "请输入密码")
    if _hash_password(data.password) != user.password_hash:
        raise HTTPException(401, "密码错误")
    # Check if user has the requested role
    user_roles = [r.strip() for r in user.role.split(",")]
    requested_role = data.role or user_roles[0]
    if requested_role not in user_roles:
        raise HTTPException(403, f"您没有 {requested_role} 权限，当前角色: {user.role}")
    # Return with the session role
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
    db.commit()
    return {"status": "ok"}
