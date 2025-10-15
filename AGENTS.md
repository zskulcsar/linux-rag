# linux-rag Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-15

## Active Technologies
- Python 3.11+ for ingestion/retrieval services; Go 1.22 for CLI (spf13/cobra) + Weaviate (local podman-compose), weaviate-python-client, Ollama (gemma3:1b, codegemma:2b, embeddinggemma), Podman, cobra CLI framework (001-linux-rag-specification)
- Python 3.11+ for ingestion/retrieval services; Go 1.22 for CLI tools (`ragman`, `ragman-admin`) using spf13/cobra + Weaviate (local podman-compose), weaviate-python-client, Ollama (gemma3:1b, codegemma:2b, embeddinggemma), Podman, python-kiwix CLI wrappers, cobra CLI framework, grpc-go/py (001-linux-rag-specification)
- Weaviate data and embeddings persisted under `/var/lib/linux-rag`, SQLite cache DB co-located under `/var/lib/linux-rag/cache`, Podman volumes for Ollama models (001-linux-rag-specification)

## Project Structure
```
src/
tests/
```

## Commands
cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style
Python 3.11+ for ingestion/retrieval services; Go 1.22 for CLI (spf13/cobra): Follow standard conventions

## Recent Changes
- 001-linux-rag-specification: Added Python 3.11+ for ingestion/retrieval services; Go 1.22 for CLI tools (`ragman`, `ragman-admin`) using spf13/cobra + Weaviate (local podman-compose), weaviate-python-client, Ollama (gemma3:1b, codegemma:2b, embeddinggemma), Podman, python-kiwix CLI wrappers, cobra CLI framework, grpc-go/py
- 001-linux-rag-specification: Added Python 3.11+ for ingestion/retrieval services; Go 1.22 for CLI (spf13/cobra) + Weaviate (local podman-compose), weaviate-python-client, Ollama (gemma3:1b, codegemma:2b, embeddinggemma), Podman, cobra CLI framework

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
