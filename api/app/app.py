from app.api.middleware import LoggingMiddleware
from app.api.routes import documents, health, jobs
from fastapi import FastAPI

app = FastAPI()

app.add_middleware(LoggingMiddleware)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(jobs.router)
