from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import config_routes, instances, logs, overview, proxy, usage, users

APP_NAME = "Shadow Admin API"

app = FastAPI(title=APP_NAME, version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(overview.router)
app.include_router(proxy.router)
app.include_router(logs.router)
app.include_router(users.router)
app.include_router(config_routes.router)
app.include_router(usage.router)
app.include_router(instances.router)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.3.0",
        "time": datetime.now(timezone.utc).isoformat(),
    }
