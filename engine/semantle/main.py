"""FastAPI 入口。

启动即加载词池 + 向量矩阵（约 0.4s，含 mmap），可选同源托管前端 dist。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .store import get_store

logging.basicConfig(
    level=os.environ.get("ARENA_LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIST = ROOT / "web" / "dist"

app = FastAPI(title="Semantle Arena", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def _warmup() -> None:
    store = get_store()
    logging.getLogger(__name__).info(
        "引擎就绪：%d 词，向量 %s，模型 %s",
        store.engine.size, store.engine.matrix.shape,
        store.engine.config,
    )


@app.get("/health")
def health() -> dict:
    store = get_store()
    return {"ok": True, "words": store.engine.size,
            "matrix": list(store.engine.matrix.shape)}


# 前端产物同源托管（存在才挂载，开发时走 Vite）
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    def _index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")

    @app.get("/{path:path}")
    def _spa(path: str) -> FileResponse:
        target = WEB_DIST / path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")
