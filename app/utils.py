import os
from dotenv import load_dotenv
from langchain_postgres.v2.engine import PGEngine

load_dotenv()

PG_CONN_STR = os.getenv("DATABASE_URL")

print("DATABASE_URL found:", bool(PG_CONN_STR))

PG_ENGINE = PGEngine.from_connection_string(PG_CONN_STR)

print("PGEngine created successfully")