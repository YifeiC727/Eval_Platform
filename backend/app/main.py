import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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


static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = os.path.join(static_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))
