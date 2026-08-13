from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import projects, import_data, assignments, annotations, arbitration, scores, export, stats, issues, qc, banks, batches

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
app.include_router(banks.router)
app.include_router(batches.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# Serve the production Vue build from the API process so the existing single
# BLB mapping (1334 -> 1997) continues to serve both UI and API.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def serve_frontend(frontend_path: str):
        requested_file = (frontend_dist / frontend_path).resolve()
        if requested_file.is_relative_to(frontend_dist.resolve()) and requested_file.is_file():
            return FileResponse(requested_file)

        index_file = frontend_dist / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404)
