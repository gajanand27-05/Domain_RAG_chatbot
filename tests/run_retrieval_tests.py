"""Retrieval evaluation harness for tests/test_questions.csv.

Builds the FAISS index from documents/*.pdf if it does not exist yet, then
for every test question retrieves the top-K chunks and auto-checks:

  * retrieval correctness - top-1 source matches expected_source
    (for multi-document questions: every expected source appears in top-K)
  * page correctness      - top-1 chunk page matches expected_page (if given)

Answer correctness, groundedness and refusal quality are manual checks:
the expected answer is printed next to the retrieved context so you can
grade them while watching the Streamlit app (the "Retrieved Context" panel
shows the same chunks the LLM saw).

Usage (project root, venv activated):
    python tests/run_retrieval_tests.py
"""
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import config  # noqa: E402
from rag_pipeline import build_index, load_index, search_relevance  # noqa: E402
from vector_store import index_exists  # noqa: E402

CSV_PATH = os.path.join(HERE, "test_questions.csv")
MANUAL_CATEGORIES = {"not_available", "prompt_injection"}


def ensure_index():
    if index_exists(config.VSTORE_DIR):
        print(f"Using existing index at {config.VSTORE_DIR}\n")
        return
    pdfs = [
        os.path.join(config.DOCUMENTS_DIR, f)
        for f in sorted(os.listdir(config.DOCUMENTS_DIR))
        if f.lower().endswith(".pdf")
    ]
    if not pdfs:
        sys.exit("No PDFs in documents/. Run first: python scripts/generate_sample_documents.py")
    print(f"Building index from {len(pdfs)} PDFs (first run downloads the embedding model)...\n")
    pages, chunks, errors = build_index(pdfs, config.VSTORE_DIR)
    for error in errors:
        print("WARNING:", error)
    print(f"Built index: {pages} pages, {chunks} chunks.\n")


def main():
    k = config.RETRIEVAL_TOP_K
    ensure_index()
    db = load_index(config.VSTORE_DIR)

    with open(CSV_PATH, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    print(f"Top-K = {k}\n")
    retrieval_pass = retrieval_total = 0
    timings = []

    for n, row in enumerate(rows, 1):
        question = row["question"].strip()
        expected_src = row["expected_source"].strip()
        expected_page = row["expected_page"].strip()
        category = row["category"].strip()

        t0 = time.perf_counter()
        results = search_relevance(config.VSTORE_DIR, question, k=k, vectorstore=db)
        timings.append((time.perf_counter() - t0) * 1000)

        top_doc, top_sim = results[0] if results else (None, None)
        top_src = os.path.basename(top_doc.metadata.get("source", "")) if top_doc else "(none)"
        top_page = top_doc.metadata.get("page") if top_doc else "?"

        print(f"[{n:2d}] {question}")
        print(f"     category={category}   retrieval={timings[-1]:.0f} ms")
        print(f"     expected source: {expected_src}   expected page: {expected_page or 'n/a'}")
        if top_doc is not None:
            print(f"     top-1 retrieved: {top_src}, page {top_page}   similarity: {top_sim:.2f}")
        print(f"     expected answer: {row['expected_answer'].strip()}")

        if category in MANUAL_CATEGORIES:
            print("     CHECK: manual — expect the LLM to REFUSE (no fabrication).")
            print("     Retrieved context (for manual review):")
            for doc, sim in results:
                print(
                    f"       - {os.path.basename(doc.metadata.get('source', ''))} "
                    f"p{doc.metadata.get('page')} [{doc.metadata.get('chunk_id')}] "
                    f"sim={sim:.2f}: {doc.page_content[:100].strip()}..."
                )
            print()
            continue

        expected_set = {s.strip() for s in expected_src.split(";") if s.strip()}
        retrieved_set = {
            os.path.basename(doc.metadata.get("source", "")) for doc, _ in results
        }
        source_ok = top_src in expected_set
        if len(expected_set) > 1:
            source_ok = source_ok and expected_set <= retrieved_set
        page_ok = True
        if expected_page:
            page_ok = str(top_page) == expected_page

        if source_ok:
            retrieval_pass += 1
        retrieval_total += 1

        status = "PASS" if source_ok and page_ok else "FAIL"
        if not source_ok:
            status += f" (source mismatch, expected {', '.join(sorted(expected_set))})"
        if not page_ok:
            status += f" (page mismatch, got {top_page})"
        print(f"     {status}")
        print("     Retrieved context:")
        for doc, sim in results:
            print(
                f"       - {os.path.basename(doc.metadata.get('source', ''))} "
                f"p{doc.metadata.get('page')} [{doc.metadata.get('chunk_id')}] "
                f"sim={sim:.2f}: {doc.page_content[:100].strip()}..."
            )
        print()

    avg_ms = sum(timings) / len(timings) if timings else 0
    print("=" * 72)
    print(f"Retrieval correctness: {retrieval_pass}/{retrieval_total} "
          f"auto-checkable questions passed")
    print(f"Average retrieval time: {avg_ms:.0f} ms (response time metric)")
    print()
    print("Manual grading checklist (watch the Streamlit app while grading):")
    print("  - Answer correctness: answer matches 'expected answer' above")
    print("  - Groundedness:      every claim in the answer exists in the Retrieved Context")
    print("  - Refusal quality:   not_available/injection rows refuse without inventing facts")
    print("  - Source quality:    citations show the right document + page, no duplicates")
    sys.exit(0 if retrieval_pass == retrieval_total else 1)


if __name__ == "__main__":
    main()
