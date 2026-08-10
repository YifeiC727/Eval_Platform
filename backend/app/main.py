from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import projects, import_data, assignments, annotations, arbitration, scores, export, stats, issues, qc

Base.metadata.create_all(bind=engine)

app = FastAPI(title="V6 T2V 评测平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(projects.users_router)
app.include_router(import_data.router)
app.include_router(import_data.questions_router)
app.include_router(import_data.videos_router)
app.include_router(assignments.router)
app.include_router(annotations.router)
app.include_router(arbitration.router)
app.include_router(scores.router)
app.include_router(export.router)
app.include_router(stats.router)
app.include_router(issues.router)
app.include_router(qc.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
