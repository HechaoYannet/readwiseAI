"""ReadWise AI – FastAPI application entry point."""
import logging

from fastapi import FastAPI

from app.api.routes import attempts, callback, results

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ReadWise AI", version="0.1.0")

# Public API
app.include_router(attempts.router, prefix="/api")
app.include_router(results.router, prefix="/api")

# Internal callback (sub-agent → orchestrator)
app.include_router(callback.router, prefix="/internal")


@app.get("/")
async def root():
    return {"message": "ReadWise AI is running"}
