"""Retrieval + answer generation pipeline.

Flow: question -> embed -> FAISS top-K -> strict prompt -> LLM -> grounded answer.
Only the retrieved chunks (never the whole PDF collection) are sent to the LLM.
"""
import os

import config
from document_loader import DocumentLoadError, load_pdf
from llm import get_llm_provider
from prompt import build_prompt
from vector_store import create_embeddings, load_vectorstore, save_vectorstore

NOT_FOUND_MESSAGE = "I could not find this information in the uploaded documents."


def load_index(vectorstore_dir):
    """Load the saved FAISS index, with a friendly error if it does not exist."""
    try:
        return load_vectorstore(vectorstore_dir)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "No processed documents found yet. Upload PDFs and click 'Process Documents' first."
        ) from exc


def build_index(pdf_paths, out_dir):
    """Load PDFs, chunk + embed them and save the FAISS index to out_dir.

    Returns (num_pages, num_chunks, errors). Individual unreadable PDFs are
    skipped and reported in errors instead of aborting the whole run.
    """
    all_docs, errors = [], []
    for path in pdf_paths:
        try:
            all_docs.extend(load_pdf(path))
        except DocumentLoadError as exc:
            errors.append(str(exc))

    if not all_docs:
        detail = " ".join(errors) if errors else "The PDFs may be scanned images; OCR is not enabled."
        raise RuntimeError(f"No extractable text found in the selected PDFs. {detail}")

    vectorstore, chunk_count = create_embeddings(all_docs)
    save_vectorstore(vectorstore, out_dir)
    return len(all_docs), chunk_count, errors


def search_relevance(vectorstore_dir, question, k=None, vectorstore=None):
    """Retrieve the top-K chunks as (document, similarity) pairs.

    Similarity is cosine similarity in [0, 1] - higher is more similar.
    """
    k = k or config.RETRIEVAL_TOP_K
    db = vectorstore if vectorstore is not None else load_index(vectorstore_dir)
    # FAISS returns L2 distance on L2-normalised vectors; convert it to
    # cosine similarity: cosine = 1 - d^2 / 2
    results = db.similarity_search_with_score(question, k=k)
    return [(doc, max(0.0, min(1.0, 1.0 - float(score) ** 2 / 2.0))) for doc, score in results]


def generate_answer(vectorstore_dir, question, k=None, vectorstore=None):
    """Retrieve context and generate a grounded answer via the configured LLM."""
    results = search_relevance(vectorstore_dir, question, k=k, vectorstore=vectorstore)
    if not results:
        return NOT_FOUND_MESSAGE, []

    context = "\n\n---\n\n".join(
        f"[{os.path.basename(doc.metadata.get('source', 'Unknown'))}, "
        f"Page {doc.metadata.get('page', '?')}, {doc.metadata.get('chunk_id', '?')}]:\n{doc.page_content}"
        for doc, _ in results
    )

    system_prompt, user_prompt = build_prompt(context, question)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    answer = get_llm_provider().generate(messages)
    if not answer:
        answer = NOT_FOUND_MESSAGE
    return answer, results
