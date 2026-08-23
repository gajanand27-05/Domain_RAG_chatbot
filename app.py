"""Streamlit UI: document upload, processing controls, chat with citations.

The star feature is the expandable "Retrieved Context" panel under every
answer - it shows exactly which chunks (document, page, similarity, chunk id)
the RAG retrieved, so you can verify the answer is grounded in the PDFs.
"""
import os
import shutil

import streamlit as st

import config
from llm import LLMProviderError, get_llm_provider
from rag_pipeline import build_index, generate_answer
from vector_store import index_exists

st.set_page_config(page_title="RAG Chatbot", page_icon="📚", layout="wide")

GREETING = "Hello! Upload a PDF and start asking questions."


def _init_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": GREETING}]
    if "meta" not in st.session_state:
        st.session_state.meta = {}
    if "saved_files" not in st.session_state:
        st.session_state.saved_files = set()


def clear_chat():
    st.session_state.messages = [{"role": "assistant", "content": GREETING}]
    st.session_state.meta = {}


def clear_documents():
    for name in os.listdir(config.DOCUMENTS_DIR):
        if name.lower().endswith(".pdf"):
            os.remove(os.path.join(config.DOCUMENTS_DIR, name))
    shutil.rmtree(config.VSTORE_DIR, ignore_errors=True)
    st.session_state.saved_files = set()
    clear_chat()


def process_documents():
    pdf_files = [
        os.path.join(config.DOCUMENTS_DIR, f)
        for f in sorted(os.listdir(config.DOCUMENTS_DIR))
        if f.lower().endswith(".pdf")
    ]
    if not pdf_files:
        st.error("No PDF files found in the documents folder.")
        return
    with st.spinner("Extracting, chunking and embedding documents..."):
        try:
            pages, chunks, errors = build_index(pdf_files, config.VSTORE_DIR)
        except Exception as exc:
            st.error(f"Processing failed: {exc}")
            return
    for error in errors:
        st.warning(f"Some documents could not be processed: {error}")
    st.success(
        f"Processed {len(pdf_files)} PDFs ({pages} pages, {chunks} chunks). "
        "You can now ask questions!"
    )


def _unique_sources(results):
    """Deduplicate (file, page) citations while keeping order."""
    seen, sources = set(), []
    for doc, _ in results:
        key = (
            os.path.basename(doc.metadata.get("source", "Unknown")),
            doc.metadata.get("page", "?"),
        )
        if key not in seen:
            seen.add(key)
            sources.append(key)
    return sources


def _render_sources(results):
    sources = _unique_sources(results)
    if not sources:
        return
    st.markdown("**Sources:**")
    for i, (name, page) in enumerate(sources, 1):
        st.markdown(f"{i}. {name} — Page {page}")


def _render_context(results):
    """The demo panel: exactly what the RAG retrieved, with similarity scores."""
    with st.expander("🔍 Retrieved Context", expanded=False):
        for i, (doc, similarity) in enumerate(results, 1):
            name = os.path.basename(doc.metadata.get("source", "Unknown"))
            page = doc.metadata.get("page", "?")
            chunk_id = doc.metadata.get("chunk_id", "?")
            st.markdown(f"**Retrieved Context #{i}**")
            st.markdown(f"{name}\nPage {page}\nSimilarity: {similarity:.2f}\nChunk ID: `{chunk_id}`")
            st.caption(f"...{doc.page_content.strip()[:300]}...")
            st.divider()


def main():
    st.title("📚 Domain-Specific RAG Chatbot")
    st.caption(
        "Upload PDF documents and ask questions — answers are grounded ONLY in your documents. "
        "Open the “Retrieved Context” panel to see exactly what was retrieved."
    )
    _init_state()

    with st.sidebar:
        st.header("📄 Documents")
        uploaded_files = st.file_uploader(
            "Choose PDF file(s)",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_uploader",
        )
        if uploaded_files:
            os.makedirs(config.DOCUMENTS_DIR, exist_ok=True)
            for f in uploaded_files:
                if f.size > config.MAX_PDF_MB * 1024 * 1024:
                    st.error(f"⚠️ {f.name} exceeds the {config.MAX_PDF_MB} MB limit and was skipped.")
                    continue
                file_key = f"{f.name}:{f.size}"
                if file_key in st.session_state.saved_files:
                    continue
                with open(os.path.join(config.DOCUMENTS_DIR, f.name), "wb") as fh:
                    fh.write(f.getbuffer())
                st.session_state.saved_files.add(file_key)
                st.success(f"Saved: {f.name}")

        st.divider()
        if st.button("🔧 Process Documents", type="primary", width="stretch"):
            process_documents()
        if st.button("♻️ Rebuild Index", width="stretch"):
            shutil.rmtree(config.VSTORE_DIR, ignore_errors=True)
            process_documents()
        if st.button("🧹 Clear Documents", type="secondary", width="stretch"):
            clear_documents()

        top_k = st.slider(
            "Retrieval Top-K",
            min_value=1,
            max_value=10,
            value=config.RETRIEVAL_TOP_K,
            help="Number of document chunks retrieved per question.",
        )

        st.divider()
        st.info("Documents:")
        pdf_files = [f for f in os.listdir(config.DOCUMENTS_DIR) if f.lower().endswith(".pdf")]
        if pdf_files:
            for name in sorted(pdf_files):
                st.text(f"  📎 {name}")
        else:
            st.text("  No PDFs uploaded yet.")

        index_ready = index_exists(config.VSTORE_DIR)
        if index_ready:
            st.success("✅ Vector index ready")
        else:
            st.warning("⚠️ No index yet — process the documents first")

        provider = get_llm_provider()
        if provider.is_configured():
            st.caption(f"LLM provider: **{provider.name}** ({provider.model_name()})")
        else:
            st.caption(
                f"LLM provider: **{provider.name}** — API key missing. "
                "Set it in .env (see .env.example), then ask questions."
            )

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            meta = st.session_state.meta.get(idx)
            if msg["role"] == "assistant" and meta:
                _render_sources(meta)
                _render_context(meta)

    if prompt := st.chat_input("Ask a question about your documents..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching documents..."):
                try:
                    answer, results = generate_answer(config.VSTORE_DIR, prompt, k=top_k)
                except LLMProviderError as exc:
                    st.error(str(exc))
                    answer = "The question could not be answered (LLM not configured)."
                    results = []
                except Exception as exc:
                    st.error(f"An error occurred: {exc}")
                    answer = "An error occurred while processing your question."
                    results = []

                st.markdown(answer)
                if results:
                    _render_sources(results)
                    _render_context(results)

        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.meta[len(st.session_state.messages) - 1] = results

    st.divider()
    st.caption("Answers are generated from uploaded documents only. Verify important information yourself.")


if __name__ == "__main__":
    main()
