# AGNES | Agricultural Extension Chatbot & Research Assistant

AGNES (named for the AG Extension offices she serves) is a work project — a
domain-specific AI chatbot and research database built to support Utah State
University Extension offices. Rather than searching through hundreds of documents
manually, extension agents can ask AGNES a question and get an answer drawn
directly from a vetted library of factsheets.

## What it does

AGNES is backed by a vectorized database of approximately 1,200 Extension
factsheets stored in OpenAI's vector store. The frontend chat interface lets
users query that knowledge base conversationally, with responses grounded in
the actual factsheet content rather than general internet knowledge.

## What's in this repo (and why you might care)

- `main.py` — FastAPI application entry point; handles routing, the OpenAI
  client, and the health check endpoint
- `api_assistant/` — Core assistant logic and OpenAI vector store integration
- `chat/` — Frontend chat interface served as static files
- `chatbot_site/` — Django project configuration including CSRF and allowed
  hosts settings
- `Backend/` — Supporting backend files
- `Dockerfile` / `Procfile` — Container and deployment configuration for
  hosting the app
- `requirements.txt` — Python dependencies
- `extension-products_2026_02_06_with-domain.csv` — Source data used to
  build and organize the factsheet knowledge base

## Tech stack

- Django + FastAPI hybrid backend
- OpenAI Assistants API with vectorized document retrieval
- Uvicorn for ASGI serving
- SQLite for lightweight local persistence
- Deployed via Docker

## Who this is for

If you are interested in how to build a retrieval-augmented chatbot grounded
in a specific document library — rather than general web knowledge — this repo
is a practical real-world example. The target users are Extension office staff
who need fast, reliable answers from a curated set of agricultural research documents.
