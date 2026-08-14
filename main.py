from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from database import create_tables, make_engine
from deps import get_current_user
from routes import auth_router, comment_router, member_router, project_router, task_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "engine"):
        app.state.engine = make_engine()
        app.state.owns_engine = True
    create_tables(app.state.engine)
    yield
    if getattr(app.state, "owns_engine", False):
        app.state.engine.dispose()


app = FastAPI(lifespan=lifespan)

app.include_router(auth_router)
app.include_router(project_router, dependencies=[Depends(get_current_user)])
app.include_router(task_router, dependencies=[Depends(get_current_user)])
app.include_router(comment_router, dependencies=[Depends(get_current_user)])
app.include_router(member_router, dependencies=[Depends(get_current_user)])