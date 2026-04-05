"""ReadWise AI – FastAPI application entry point."""
import logging

from fastapi import FastAPI

from app.api.routes import attempts, callback, results, auth, users, memory, sessions

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ReadWise AI", version="0.2.0")

# Auth & user routes
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")

# Public API
app.include_router(attempts.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")

# Internal callback (sub-agent → orchestrator)
app.include_router(callback.router, prefix="/internal")


@app.get("/")
async def root():
    return {"message": "ReadWise AI is running"}
