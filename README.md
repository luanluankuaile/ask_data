# Example LLM Application

This application uses Azure Open AI API for LLM and HuggingFace embeddings for document vectorization.

## Configuration

Create a `.env` file in the project root with your DeepSeek API key:

```bash
AZURE_OPENAI_API_KEY="********************"
AZURE_OPENAI_ENDPOINT=https://ai-proxy.lab.epam.com
OPENAI_API_VERSION=2025-04-01-preview
DATABASE_URI=postgresql://postgres:admin@localhost:5432/mydb

# students-project-13

This repository provides a small Streamlit UI that translates natural-language queries into safe, read-only SQL statements targeting a `students` table. It supports a conservative rule-based NL→SQL fallback and optional Azure OpenAI-based generation.

## Configuration

Create a `.env` file in the project root (optional) to store secrets, or export them in your shell. Example variables used by this project:

```bash
# Postgres connection string (recommended for real DB)
DATABASE_URI="postgresql://<user>:<pass>@<host>:<port>/<db>"

# Development: opt into sqlite fallback instead of DATABASE_URI
ALLOW_SQLITE_FALLBACK=0

# Optional: Azure OpenAI key and endpoint for LLM-driven generation
AZURE_OPENAI_API_KEY=""
AZURE_OPENAI_ENDPOINT=""
OPENAI_API_VERSION="2025-04-01-preview"
```

## Setup

Use either the project's `.venv` or your conda environment. Install required packages:

```bash
# If using .venv:
source .venv/bin/activate
pip install -r requirements.txt

# Or with conda:
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate myenv
pip install -r requirements.txt
```

## Run (Streamlit)

Start the app (headless mode for servers):

```bash
.venv/bin/python -m streamlit run main.py --server.port 8501 --server.headless true
```

Pass script arguments to `main.py` (optional) by adding `--` before them:

```bash
.venv/bin/python -m streamlit run main.py -- --nl "how many students enrolled on 2022?"
```

## Local development (sqlite fallback)

If you do not have Postgres available, enable sqlite fallback for quick local tests:

```bash
export ALLOW_SQLITE_FALLBACK=1
unset DATABASE_URI
# Then run Streamlit as above. The app will use ./local_test.db for simple testing.
```

## Safety & Behavior

- The app validates generated SQL and only allows single `SELECT` queries.
- If `AZURE_OPENAI_API_KEY` is not set, a small rule-based fallback handles common prompts (counts, year filters, lists).
- The sqlite fallback is for development only — do not use it in production.

## Troubleshooting

- If `conda activate` errors with `Run 'conda init'`, run:

```bash
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate myenv
```

- Check Streamlit logs: `~/.streamlit/streamlit.log` for startup/runtime errors.
- Confirm which Python/Streamlit is used: `which python` / `which streamlit`.

## Contributing

- Branch from `epam_dial_chatbot` and open a Merge Request in the remote repo when ready.

---

If you'd like I can also add a small `README` badge or an example `.env.example` file — tell me which you'd prefer.

