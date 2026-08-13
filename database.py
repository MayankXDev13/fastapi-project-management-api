from sqlalchemy import event
from sqlmodel import SQLModel, create_engine, Session
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})


def _set_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def register_foreign_keys_listener(target_engine):
    event.listen(target_engine, "connect", _set_foreign_keys)


register_foreign_keys_listener(engine)


def create_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session