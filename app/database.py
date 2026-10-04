from time import time

from dotenv import load_dotenv

from psycopg.rows import dict_row
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

load_dotenv()

SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg://{settings.database_username}:"
    f"{settings.database_password}@{settings.database_hostname}:"
    f"{settings.database_port}/{settings.database_name}"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# while True:
#     try:
#         conn=psycopg.connect(host='localhost', dbname='fastapi', user='postgres', password='postgres', row_factory=dict_row)
#         cursor=conn.cursor()
#         print("Database connection was successful!")
#         break
#     except Exception as error:
#         print("Database connection failed!")
#         print("Error: ", error)
#         time.sleep(2)   