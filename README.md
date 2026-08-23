# Domain-Specific RAG Chatbot for PDF Question Answering

A Streamlit chatbot that answers questions from **uploaded PDF documents** using
**Retrieval-Augmented Generation (RAG)**. The PDFs are the knowledge base: every
answer is grounded **only** in the chunks retrieved from them, with source
document and page citations. If the information is not in the documents, the
chatbot refuses instead of inventing an answer.

## How it works (workflow)

```
Upload PDF(s)
   │  document_loader.py        pypdf: one Document per page
   │                            (filename + page number kept, empty pages skipped)
   ▼
Chunking
   │  vector_store.py           RecursiveCharacterTextSplitter
   │                            (chunk size 900 / overlap 150, configurable)
   │                            every chunk gets a stable chunk_id, e.g. Policy.pdf-p3-c2
   ▼
Embeddings
   │  vector_store.py           sentence-transformers/all-MiniLM-L6-v2
   │                            (model name configurable, embeddings L2-normalised)
   ▼
Vector database
   │  vector_store.py           FAISS index saved locally (vector_store/saved_index)
   │                            index.index = vectors, index.pkl = metadata
   │                            (reloaded on start - no reprocessing of PDFs)
   ▼
User asks a question
   │  rag_pipeline.py           question is embedded and the top-K most similar
   │                            chunks are retrieved (K configurable, default 5)
   ▼
Answer generation
   │  rag_pipeline.py + llm.py  ONLY the retrieved chunks (with doc + page labels)
   │                            are sent to the LLM under a strict guardrail prompt
   ▼
Answer + citations
      app.py                    "Sources: 1. Policy.pdf — Page 6"
                                + expandable "Retrieved Context" panel showing
                                each retrieved chunk with document, page,
                                similarity score and chunk_id
```

### Why this is "RAG" and not just an LLM

The LLM never sees the whole PDF collection — only the top-K retrieved chunks.
The expandable **Retrieved Context** panel under every answer shows exactly what
the system retrieved (document, page, similarity, chunk id), so you can verify
the answer is grounded in the documents instead of the model's prior knowledge.

## Project structure

```
domain_rag_chatbot/
├── app.py                      # Streamlit UI (upload, chat, citations, Retrieved Context)
├── rag_pipeline.py             # build_index + retrieval + answer generation
├── document_loader.py          # PDF text extraction (pypdf), page metadata
├── vector_store.py             # chunking, embeddings, FAISS save/load
├── prompt.py                   # strict guardrail system prompt
├── llm.py                      # LLMProvider -> Groq/Gemini/OpenAI/Local
├── config.py                   # all tunables from .env (chunk size, K, model, ...)
├── requirements.txt            # runtime dependencies
├── requirements-dev.txt        # + fpdf2 (only for generating sample PDFs)
├── README.md
├── .env.example                # copy to .env and fill in your keys
├── .gitignore
├── documents/                  # sample HR policy PDFs (generated)
├── vector_store/saved_index/   # persisted FAISS index (git-ignored)
├── scripts/
│   └── generate_sample_documents.py   # (re)creates the 4 sample PDFs
└── tests/
    ├── test_questions.csv      # 20 test questions across 7 categories
    └── run_retrieval_tests.py  # retrieval evaluation harness
```

## LLM provider (configurable — nothing hard-coded)

`llm.py` implements a provider hierarchy, so the pipeline stays the same no
matter which model backs the answers:

```
LLMProvider (abstract base)
├── GroqProvider      (ChatGroq,            e.g. openai/gpt-oss-120b)
├── GeminiProvider    (ChatGoogleGenerativeAI, e.g. gemini-2.0-flash)
├── OpenAIProvider    (ChatOpenAI,          e.g. gpt-4o-mini)
└── LocalProvider     (ChatOpenAI pointed at an OpenAI-compatible local
                      server: Ollama, LM Studio, vLLM, ... e.g. a local Qwen)
```

Select the provider with `LLM_PROVIDER` in `.env` (`groq | gemini | openai |
local`). To plug in a local model later, start e.g. Ollama, set
`LLM_PROVIDER=local` and `LOCAL_MODEL_NAME=<your model>` — no code changes.

## Setup

Python 3.10+ required.

```bash
cd domain_rag_chatbot

# 1. Virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux/Mac

# 2. Install dependencies
#    (on machines without a GPU, install CPU-only torch first to skip the
#    multi-GB CUDA download):
pip install torch --index-url https://download.pytorch.org/whl/cpu   # optional, CPU-only
pip install -r requirements.txt

# 3. Configuration
copy .env.example .env           # Windows (or: cp .env.example .env)
#    edit .env: set LLM_PROVIDER and the matching API key
#    (Groq keys are free at https://console.groq.com)

# 4. Sample documents (already included; regenerate if you like)
pip install -r requirements-dev.txt
python scripts/generate_sample_documents.py

# 5. Run the app
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Usage

1. Sidebar: upload one or more PDF files (`.pdf` only, max size from `.env`).
2. **Process Documents** — extract, chunk, embed and build the FAISS index.
   **Rebuild Index** — discard the saved index and process again (use after
   changing chunk size / overlap / embedding model in `.env`).
   **Clear Documents** — remove all uploaded PDFs and the index.
3. Adjust **Retrieval Top-K** (how many chunks to retrieve per question).
4. Ask questions in the chat box. Each answer shows:
   - the grounded answer,
   - **Sources:** deduplicated list of `document — Page N`,
   - an expandable **Retrieved Context** panel: every retrieved chunk with
     document, page, similarity score and chunk_id.

### Demo walkthrough (the money shot)

Ask: **"What is the leave policy?"** and open the *Retrieved Context* panel:

```
Retrieved Context #1
Policy.pdf
Page 2
Similarity: 0.59
Chunk ID: Policy.pdf-p2-c1

"...2. Annual Leave. Every employee with at least twelve months of continuous
service earns 20 calendar days of paid annual leave per calendar year..."

Answer:
Employees are entitled to 20 calendar days of paid annual leave per year...

Sources:
1. Policy.pdf — Page 2
```

Then ask **"Who is the company CEO?"** — the documents never name a CEO, and
the chatbot must answer with the refusal message instead of inventing one.

## Testing

Twenty test questions in `tests/test_questions.csv` cover seven categories:
answers that exist, cross-document questions, multi-chunk questions,
questions with no answer, prompt-injection attempts, paraphrased wording, and
page/source verification.

CSV columns: `question, expected_source, expected_page, expected_answer, category`

Run the retrieval harness (builds the index automatically if it is missing):

```bash
python tests/run_retrieval_tests.py
```

What it checks automatically:

| Check | How |
|---|---|
| Retrieval correctness | top-1 source matches `expected_source` (multi-doc rows: all expected docs appear in top-K) |
| Page correctness | top-1 chunk page matches `expected_page` |
| Response time | retrieval latency per question (embedding + FAISS search) |

What you grade manually while watching the app (the harness prints each
`expected_answer` next to the retrieved context):

| Criterion | What to look for |
|---|---|
| Answer correctness | answer matches the expected answer |
| Groundedness | every claim in the answer exists in the Retrieved Context |
| Refusal quality | `not_available` / `prompt_injection` rows get the refusal message, no invented facts |
| Source quality | citations show the right document + page, no duplicate citations |

## Configuration reference (.env)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` / `gemini` / `openai` / `local` |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` | — | API key for the selected provider |
| `GROQ_MODEL_NAME` | `openai/gpt-oss-120b` | model name (per provider) |
| `LOCAL_BASE_URL` | `http://localhost:11434/v1` | local OpenAI-compatible endpoint |
| `LOCAL_MODEL_NAME` | `llama3.1:8b` | local model name |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | sentence-transformers model |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `900` / `150` | chunking window (recommended 700–1000 / 100–150) |
| `RETRIEVAL_TOP_K` | `5` | default retrieved chunks (UI slider overrides 1–10) |
| `MAX_PDF_MB` | `20` | upload size limit |

## Error handling

Handled gracefully with clear messages:

- **Empty / corrupted / encrypted PDFs** — skipped, reported in the sidebar,
  other documents still processed.
- **PDF with no extractable text** (e.g. scanned images) — clear error; OCR is
  an optional extension, not built in.
- **Duplicate uploads** — same file + size is not re-written.
- **Oversized uploads** — rejected against `MAX_PDF_MB`.
- **Missing FAISS index** — "Upload PDFs and click Process Documents first".
- **Missing/placeholder API key** — actionable message pointing at `.env`.
- **LLM failure / network error** — error banner, chat state stays intact.
- **Empty retrieval results** — standard refusal message.

## Responsible AI & security notes

- API keys live only in `.env` (git-ignored); `.env.example` has placeholders.
- Uploads are restricted to PDFs with a size limit.
- Document content is treated as **untrusted data**: the system prompt
  explicitly forbids the model from following instructions found inside
  retrieved documents (tested with the `prompt_injection` rows).
- Answers are model-generated from retrieved context; high-stakes information
  should be verified against the original documents (shown in the UI footer).

## Known limitations / possible extensions

- OCR for scanned PDFs.
- Multiple document collections with filters.
- Conversation memory for follow-up questions.
- FastAPI backend for mobile/web clients; Docker deployment.
- Full LLM answer-quality evaluation (e.g. LLM-as-judge) on top of the
  retrieval harness.

## License

MIT
