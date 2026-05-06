from src.dms.dms_client import DMSClient
from src.models.emb_client import EmbeddingClient
from src.models.llm_client import LLMClient
from src.qdrant.client import PlausibilityQdrantClient

llm_client = LLMClient()
dms_client = DMSClient()
qdrant_client = PlausibilityQdrantClient()
embedding_client = EmbeddingClient()
