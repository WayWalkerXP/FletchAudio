from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import DEFAULT_DB_URL
from .models import Base

def get_engine(db_url: str = DEFAULT_DB_URL): return create_engine(db_url, future=True)
def init_db(engine=None):
    engine = engine or get_engine(); Base.metadata.create_all(engine); return engine
def get_session_factory(engine=None): return sessionmaker(bind=engine or init_db(), future=True)
