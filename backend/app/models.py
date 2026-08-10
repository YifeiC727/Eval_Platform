from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class RoleEnum(str, enum.Enum):
    annotator = "annotator"
    lead = "lead"
    admin = "admin"


class AssignmentRole(str, enum.Enum):
    A = "A"
    B = "B"
    third = "third"
    expert = "expert"


class AssignmentStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    submitted = "submitted"


class ScoreEnum(str, enum.Enum):
    C = "C"
    R = "R"
    N = "N"


class FinalMethod(str, enum.Enum):
    consensus = "consensus"
    majority = "majority"
    expert = "expert"
    pending_third = "pending_third"
    pending_expert = "pending_expert"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128))
    password_plain = Column(String(50))
    display_name = Column(String(100))
    role = Column(String(50), default="annotator")
    created_at = Column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    model_version = Column(String(50))
    v6_version = Column(String(20), default="v6")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    questions = relationship("Question", back_populates="project")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(String(20), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"))
    prompt = Column(Text, nullable=False)
    language = Column(String(20))
    preprocess_note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    project = relationship("Project", back_populates="questions")
    checkpoints = relationship("Checkpoint", back_populates="question")
    videos = relationship("Video", back_populates="question")


class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String(20), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"))
    model_version = Column(String(50))
    oss_url = Column(Text)
    duration_sec = Column(Float)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    question = relationship("Question", back_populates="videos")
    assignments = relationship("Assignment", back_populates="video")


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    id = Column(Integer, primary_key=True, index=True)
    checkpoint_id = Column(String(30), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"))
    seq = Column(Integer)
    text = Column(Text, nullable=False)
    min_success_line = Column(Text)
    ability_id = Column(String(10))
    ability_name = Column(String(100))
    tag_id = Column(String(20))
    tag_name = Column(String(100))
    evidence_period = Column(String(50))
    preprocess_note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    question = relationship("Question", back_populates="checkpoints")


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    annotator_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String(10), nullable=False)
    status = Column(String(20), default="pending")
    assigned_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime)
    video = relationship("Video", back_populates="assignments")
    annotator = relationship("User")
    annotations = relationship("Annotation", back_populates="assignment")


class Annotation(Base):
    __tablename__ = "annotations"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"))
    checkpoint_id = Column(Integer, ForeignKey("checkpoints.id"))
    score = Column(String(1), nullable=False)
    fail_code = Column(String(5))
    evidence_ts = Column(String(20))
    note = Column(Text)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    assignment = relationship("Assignment", back_populates="annotations")
    checkpoint = relationship("Checkpoint")


class FinalResult(Base):
    __tablename__ = "final_results"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    checkpoint_id = Column(Integer, ForeignKey("checkpoints.id"))
    final_score = Column(String(1), nullable=False)
    final_fail_code = Column(String(5))
    method = Column(String(20), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    video = relationship("Video")
    checkpoint = relationship("Checkpoint")
