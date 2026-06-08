from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes.analysis import router as analysis_router
from app.utils.config import settings
from app.utils.storage import ensure_storage


ensure_storage()

app = FastAPI(
    title="MyCRWL Website Intelligence API",
    version="1.0.0",
    description="Local-first AI website crawler and business intelligence backend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")
app.include_router(analysis_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mycrwl-api"}
