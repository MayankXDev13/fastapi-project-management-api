from sqlalchemy import Engine, event
from sqlmodel import SQLModel, Session, create_engine

from config import DATABASE_URL


def _set_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def register_foreign_keys_listener(target_engine: Engine) -> None:
    event.listen(target_engine, "connect", _set_foreign_keys)


def make_engine(
    url: str = DATABASE_URL, *, echo: bool = True
) -> Engine:
    engine = create_engine(
        url, echo=echo, connect_args={"check_same_thread": False}
    )
    register_foreign_keys_listener(engine)
    return engine


def create_tables(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


def get_session(request):
    """One session per request, from the engine owned by the app (or the tests)."""
    with Session(request.app.state.engine) as session:
        yield session