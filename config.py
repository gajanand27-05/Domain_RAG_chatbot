"""Central configuration.

Every tunable of the pipeline is read from the environment (see .env.example)
with a sensible default, so behaviour can be changed without editing code.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Paths
DOCUMENTS_DIR = "documents"
VSTORE_DIR = os.path.join("vector_store", "saved_index")

# Chunking (suggested range: size 700-1000, overlap 100-150)
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# Embeddings (configurable sentence-transformers model)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# Retrieval
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))

# Upload limits
MAX_PDF_MB = int(os.getenv("MAX_PDF_MB", "20"))
