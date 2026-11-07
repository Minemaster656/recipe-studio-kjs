from openai import Client
from emb_api import EmbeddingClient, SearchIndex

client = Client(base_url="http://127.0.0.1:9931/v1")
MODEL = "llm"
eclient = EmbeddingClient("http://127.0.0.1:9931/v1", "embeddinggemma2")
idx = SearchIndex("embeddings.db", client=eclient)
