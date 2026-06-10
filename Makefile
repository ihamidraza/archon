# Archon — developer task runner
# All commands run inside the uv-managed Python 3.12 environment.

.DEFAULT_GOAL := help
.PHONY: help setup env-check ingest chat run test eval lint fmt clean ui-install ui ui-build

PY := uv run

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create the py3.12 env and install all dependencies
	uv python install 3.12
	uv sync --extra dev
	@echo "✅ Environment ready. Next: cp .env.example .env  (then add LANGCHAIN_API_KEY)"

env-check: ## Verify ollama models + settings load correctly
	$(PY) python -m backend.scripts.env_check

ingest: ## Generate synthetic KB (if needed) and build the Chroma vector store
	$(PY) python -m backend.scripts.ingest

chat: ## Run the terminal chat loop against the agent graph
	$(PY) python -m backend.scripts.chat_cli

run: ## Start the FastAPI backend (http://localhost:8000)
	$(PY) uvicorn backend.app.main:app --reload --port 8000

ui-install: ## Install the Next.js frontend dependencies
	cd frontend && npm install

ui: ## Start the Next.js dev server (http://localhost:3000)
	cd frontend && npm run dev

ui-build: ## Production build of the frontend (type-check + lint)
	cd frontend && npm run build

test: ## Run the pytest suite
	$(PY) pytest -q

eval: ## Run LangSmith evaluation suite
	$(PY) python -m backend.evals.run

lint: ## Lint with ruff
	$(PY) ruff check .

fmt: ## Auto-format with ruff
	$(PY) ruff format . && $(PY) ruff check --fix .

clean: ## Remove caches and local state (keeps .env)
	rm -rf .pytest_cache .ruff_cache backend/data/chroma/* backend/data/checkpoints.sqlite*
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
