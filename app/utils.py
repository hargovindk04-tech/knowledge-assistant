import os
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.v2.engine import PGEngine
from langchain_postgres.v2.async_vectorstore import AsyncPGVectorStore
#from langchain_huggingface import HuggingFaceEmbeddings

PG_CONN_STR = os.getenv("DATABASE_URL")

PG_ENGINE = PGEngine.from_connection_string(PG_CONN_STR)

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
#embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


async def get_vector_store()->AsyncPGVectorStore:
    return await AsyncPGVectorStore.create(
        engine=PG_ENGINE,
        embedding_service=embeddings,
        table_name="langchain_pg_embedding",
        metadata_json_column="langchain_metadata",
        metadata_columns=["category"]
    )

