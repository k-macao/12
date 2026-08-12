"""FastAPI application exposing the collected A-share data plus a small UI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..service import Collector
from ..sources.tencent import DataSourceError, TencentSource, normalize_code
from ..storage import DEFAULT_DB, Storage

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str | Path = DEFAULT_DB) -> FastAPI:
    storage = Storage(db_path)
    source = TencentSource()
    collector = Collector(storage, source)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        collector.close()
        storage.close()

    app = FastAPI(title="A 股行情 Agent", version="0.1.0", lifespan=lifespan)

    def get_storage() -> Storage:
        return storage

    @app.get("/api/stats")
    def stats(db: Storage = Depends(get_storage)) -> dict:
        return db.stats()

    @app.get("/api/quotes")
    def quotes(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        sort: str = "change_pct",
        desc: bool = True,
        keyword: str | None = None,
        db: Storage = Depends(get_storage),
    ) -> dict:
        try:
            rows = db.latest_quotes(limit=limit, offset=offset, order_by=sort,
                                    desc=desc, keyword=keyword)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"items": rows, "count": len(rows)}

    @app.get("/api/quotes/{code}")
    def quote(code: str, db: Storage = Depends(get_storage)) -> dict:
        symbol = _normalize(code)
        rows = db.latest_quotes(limit=1, keyword=symbol)
        if not rows:
            raise HTTPException(status_code=404, detail=f"{code} 暂无数据，请先抓取")
        return rows[0]

    @app.get("/api/candles/{code}")
    def candles(
        code: str,
        period: str = Query("day", pattern="^(day|week|month)$"),
        limit: int = Query(240, ge=10, le=1000),
        refresh: bool = False,
        db: Storage = Depends(get_storage),
    ) -> dict:
        symbol = _normalize(code)
        rows = db.candles(symbol, period, limit)
        if refresh or not rows:
            try:
                collector.fetch_candles([symbol], period=period, count=max(limit, 320))
            except DataSourceError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            rows = db.candles(symbol, period, limit)
        return {"code": symbol, "period": period, "items": rows}

    @app.post("/api/refresh")
    def refresh(codes: list[str] | None = None) -> dict:
        try:
            result = collector.fetch_quotes(codes)
        except DataSourceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"saved": result.quotes}

    @app.get("/api/search")
    def search(keyword: str, limit: int = Query(10, ge=1, le=50)) -> dict:
        return {"items": source.search(keyword, limit=limit)}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _normalize(code: str) -> str:
    try:
        return normalize_code(code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
