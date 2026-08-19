# app/api.py
from __future__ import annotations
import asyncio, time
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse



app = FastAPI(title="Knowledge Assistant")

# Static frontend
static_dir = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")




@app.get("/")
async def root_page():
    return FileResponse(static_dir / "index.html")
