from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import settings
from app.routes.analysis import router
from app.utils.logging import setup_logging, get_logger

setup_logging("DEBUG" if settings.app_env == "dev" else "INFO")
logger = get_logger(__name__)

app = FastAPI(
    title="LLM Backtesting Bot",
    description="LLM-assisted technical indicator backtesting for weekly/monthly OHLCV data.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve React build in production
static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(static_dir):
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = os.path.join(static_dir, "index.html")
        return FileResponse(index)

logger.info("Backend started – model: %s, env: %s", settings.openrouter_model, settings.app_env)
