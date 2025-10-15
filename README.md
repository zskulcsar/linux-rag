# RAG System for Linux

## Description

A simple RAG system for Linux that runs locally. It should be using the man pages as well as some pre-defined wiki sources using kiwix. The aim here is to have a simple interface like `man` but with the ability to ask more complicated questions, rather than just bring up man.

## Technology

* Weavieate as a vector database and general glue
* Ollama for running modells locally
* Podman for gluing everthing together

### Setup

* specify init --ai codex --script sh linux-rag
* create the `.envrc` file and `direnv allow .` for automatic loading. The file should have:
    * `export CODEX_HOME=/home/zsoltk/git/linux-rag/.codex` for Codex
    * `export CONTEXT7_API_KEY=<API_KEY>` for Context7 MCP server
* run `codex` in current folder, sign-in (or provide API key) and allow it to work in the current folder
* modify `.codex/config.toml` and add Context7 MCP as follows:
```
[mcp_servers.context7]
args = ["-y", "@upstash/context7-mcp"]
command = "npx"
```
