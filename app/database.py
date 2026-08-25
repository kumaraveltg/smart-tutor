from importlib.metadata import metadata
from sqlalchemy import create_engine,MetaData
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

url = f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
engine = create_engine(url)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base(metadata=MetaData(schema="smarttutor"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()