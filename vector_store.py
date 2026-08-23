"""Embeddings + FAISS vector store.

Chunks keep their source/page metadata and receive a stable chunk_id
(e.g. Policy.pdf-p3-c2). Embeddings are L2-normalised, so FAISS
distances translate directly to cosine similarity.
"""
import os

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

import config


def get_embeddings():
    """Create the configurable Sentence Transformers embedding model."""
    return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)


def _assign_chunk_ids(chunks):
    """Give every chunk a stable id like Policy.pdf-p3-c2 (page 3, chunk 2)."""
    counters = {}
    for chunk in chunks:
        source = os.path.basename(chunk.metadata.get("source", "unknown"))
        page = chunk.metadata.get("page", 0)
        key = (source, page)
        counters[key] = counters.get(key, 0) + 1
        chunk.metadata["chunk_id"] = f"{source}-p{page}-c{counters[key]}"
    return chunks


def create_embeddings(documents):
    """Chunk the documents, embed the chunks and store them in FAISS.

    Returns (vectorstore, num_chunks).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = _assign_chunk_ids(splitter.split_documents(documents))
    vectorstore = FAISS.from_documents(chunks, get_embeddings(), normalize_L2=True)
    return vectorstore, len(chunks)


def save_vectorstore(vectorstore, path=None):
    """Persist the FAISS index and its metadata to disk.

    index.index holds the vectors, index.pkl holds the chunk metadata, so
    the index can be reloaded without reprocessing the PDFs.
    """
    path = path or config.VSTORE_DIR
    os.makedirs(path, exist_ok=True)
    vectorstore.save_local(path)


def load_vectorstore(path=None):
    """Load a saved FAISS index from disk."""
    path = path or config.VSTORE_DIR
    return FAISS.load_local(path, get_embeddings(), allow_dangerous_deserialization=True)


def index_exists(path=None):
    """True if a saved FAISS index is present in path (no rebuild needed)."""
    path = path or config.VSTORE_DIR
    if not os.path.isdir(path):
        return False
    return any(name in os.listdir(path) for name in ("index.faiss", "index.index"))
