from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import create_tables
from middleware.auth_middleware import AuthMiddleware
from routes import auth_router, comment_router, member_router, project_router, task_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(task_router)
app.include_router(comment_router)
app.include_router(member_router)
