.DEFAULT_GOAL := help

PYTHON_DISTRIBUTION := .venv/bin/python -m
PYTHON_DIRS := $(strip $(foreach dir,src/python tests/python,$(if $(wildcard $(dir)),$(dir),)))
GO_ROOT := src/go
GO_FILES := $(shell find $(GO_ROOT) -name '*.go' 2>/dev/null)
GO_PACKAGES := ./...

TOOLS_BIN := $(abspath .tools/bin)

GOLANGCI_LINT ?= $(TOOLS_BIN)/golangci-lint
GOVULNCHECK ?= $(TOOLS_BIN)/govulncheck
PROTO_SRC_DIR := specs/001-linux-rag-specification/contracts
PROTO_FILE := $(PROTO_SRC_DIR)/rag_service.proto

.PHONY: help init init-python init-go lint lint-python lint-go format format-python format-go \
	typecheck typecheck-python test test-python test-go build-cli proto clean \
	test-integration coverage-python security-audit security-audit-python security-audit-go \
	security-audit-fix go-audit-fix pip-audit-fix stack-up stack-down

help:
	@printf "Available targets:\n"
	@printf "  init               Install local dev dependencies (Python & Go)\n"
	@printf "  lint               Run Python lint (ruff) and Go lint (golangci-lint if available)\n"
	@printf "  format             Format Python (black) and Go (gofmt) sources\n"
	@printf "  typecheck          Type-check Python sources with mypy\n"
	@printf "  test               Run unit test suites (pytest + go test)\n"
	@printf "  build-cli          Compile ragman and ragman-admin binaries into ./bin\n"
	@printf "  proto              Regenerate Python/Go gRPC stubs from contracts\n"
	@printf "  clean              Remove build artifacts, caches, and generated files\n"
	@printf "  test-integration   Execute Python integration test suite\n"
	@printf "  coverage-python    Run pytest with coverage reporting\n"
	@printf "  security-audit     Run Python (pip-audit) and Go (govulncheck) vulnerability scans\n"
	@printf "  security-audit-fix  Run vulnerability scans with optional remediation\n"
	@printf "  pip-audit-fix      Run pip-audit dry run, then optionally apply fixes\n"
	@printf "  stack-up           Run the ragman-admin command to start-up the podman-compose stack"
	@printg "  stack-down         Run podman-compose (no down yet in ragman-admin) to stop the stack"

lint: lint-python lint-go

lint-python:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) ruff check $(PYTHON_DIRS); \
	else \
		echo "No Python directories found; skipping ruff check."; \
	fi

lint-go:
	@if [ -d "$(GO_ROOT)" ]; then \
		if ! (cd $(GO_ROOT) && go list ./... >/dev/null 2>&1); then \
			echo "Skipping Go lint; go list ./... failed (run 'go mod tidy'?)."; \
		elif [ -x "$(GOLANGCI_LINT)" ]; then \
			cd $(GO_ROOT) && "$(GOLANGCI_LINT)" run --modules-download-mode=mod ./...; \
		elif command -v golangci-lint >/dev/null 2>&1; then \
			cd $(GO_ROOT) && golangci-lint run --modules-download-mode=mod ./...; \
		else \
			echo "golangci-lint not found; skipping Go lint."; \
		fi; \
	else \
		echo "Go source directory not found; skipping Go lint."; \
	fi

format: format-python format-go

format-python:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) black $(PYTHON_DIRS); \
	else \
		echo "No Python directories found; skipping black format."; \
	fi

format-go:
	@if [ -n "$(GO_FILES)" ]; then \
		gofmt -w $(GO_FILES); \
	else \
		echo "No Go files found; skipping gofmt."; \
	fi

typecheck: typecheck-python

typecheck-python:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) mypy $(PYTHON_DIRS); \
	else \
		echo "No Python directories found; skipping mypy type checks."; \
	fi

test: test-python test-go

test-python:
	$(PYTHON_DISTRIBUTION) pytest

test-go:
	@if [ -d "$(GO_ROOT)" ]; then \
		cd $(GO_ROOT) && GOCACHE=$(shell pwd)/.gocache GOMODCACHE=$(shell pwd)/.gomodcache go test $(GO_PACKAGES); \
	else \
		echo "Go source directory not found; skipping go test."; \
	fi

build-cli:
	@if [ -d "$(GO_ROOT)" ]; then \
		mkdir -p bin; \
		cd $(GO_ROOT) && GOCACHE=$(shell pwd)/.gocache GOMODCACHE=$(shell pwd)/.gomodcache go build -o $(shell pwd)/bin/ragman ./cmd/ragman \
		&& GOCACHE=$(shell pwd)/.gocache GOMODCACHE=$(shell pwd)/.gomodcache go build -o $(shell pwd)/bin/ragman-admin ./cmd/ragman-admin; \
	else \
		echo "Go source directory not found; skipping CLI build."; \
	fi

proto:
	$(PYTHON_DISTRIBUTION) grpc_tools.protoc -I=$(PROTO_SRC_DIR) --python_out=src/python/linux_rag/contracts --grpc_python_out=src/python/linux_rag/contracts $(PROTO_FILE)
	protoc -I=$(PROTO_SRC_DIR) --go_out=$(GO_ROOT) --go-grpc_out=$(GO_ROOT) $(PROTO_FILE)

clean:
	rm -rf bin .gocache .gomodcache .mypy_cache .pytest_cache .ruff_cache .uvcache
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

test-integration:
	$(PYTHON_DISTRIBUTION) pytest tests/python/integration

coverage-python:
	$(PYTHON_DISTRIBUTION) pytest --cov=src/python/linux_rag --cov-report=term-missing

init: init-python init-go

init-python:
	@if command -v uv >/dev/null 2>&1; then \
		uv sync; \
	else \
		echo "uv not found; please install uv before running make init-python."; \
		exit 1; \
	fi

init-go:
	@if [ -d "$(GO_ROOT)" ]; then \
		if command -v go >/dev/null 2>&1; then \
			cd $(GO_ROOT) && go mod download; \
			mkdir -p $(TOOLS_BIN); \
			GOBIN=$(TOOLS_BIN) go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest; \
			GOBIN=$(TOOLS_BIN) go install golang.org/x/vuln/cmd/govulncheck@latest; \
			echo "Go tools installed to $(TOOLS_BIN). Consider adding it to your PATH."; \
		else \
			echo "Go toolchain not found; skipping Go dependency installation."; \
		fi; \
	else \
		echo "Go source directory not found; skipping Go init."; \
	fi

security-audit: security-audit-python security-audit-go

security-audit-python:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) pip_audit; \
	else \
		echo "No Python directories found; skipping pip-audit."; \
	fi

security-audit-go:
	@if [ -d "$(GO_ROOT)" ]; then \
		if [ -x "$(GOVULNCHECK)" ]; then \
			cd $(GO_ROOT) && "$(GOVULNCHECK)" ./...; \
		elif command -v govulncheck >/dev/null 2>&1; then \
			cd $(GO_ROOT) && govulncheck ./...; \
		else \
			echo "govulncheck not found; skipping Go vulnerability scan."; \
		fi; \
	else \
		echo "Go source directory not found; skipping Go vulnerability scan."; \
	fi

security-audit-fix: pip-audit-fix go-audit-fix

pip-audit-fix:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) pip_audit --fix --dry-run; \
		status=$$?; \
		if [ $$status -eq 0 ]; then \
			echo "No vulnerabilities found by pip-audit."; \
		elif [ $$status -eq 1 ]; then \
			read -p "Apply fixes reported by pip-audit? [y/N]: " reply; \
			case "$$reply" in \
				[yY][eE][sS]|[yY]) \
					$(PYTHON_DISTRIBUTION) pip_audit --fix ;; \
				*) \
					echo "Skipping pip-audit fixes." ;; \
				esac; \
		else \
			echo "pip-audit failed (exit $$status)."; \
			exit $$status; \
		fi; \
	else \
		echo "No Python directories found; skipping pip-audit fix."; \
	fi

go-audit-fix:
	@if [ -d "$(GO_ROOT)" ]; then \
		BIN="$(GOVULNCHECK)"; \
		if [ -x "$$BIN" ]; then \
			cd $(GO_ROOT) && "$$BIN" ./...; \
			status=$$?; \
		elif command -v govulncheck >/dev/null 2>&1; then \
			cd $(GO_ROOT) && govulncheck ./...; \
			status=$$?; \
		else \
			echo "govulncheck not found; skipping Go vulnerability remediation."; \
			exit 0; \
		fi; \
		if [ "$$status" = "0" ]; then \
			continue \
		elif [ "$$status" = "3" ]; then \
			read -p "Attempt Go dependency updates to address findings? [y/N]: " reply; \
			case "$$reply" in \
				[yY][eE][sS]|[yY]) \
					cd $(GO_ROOT) && go get -u ./... && go mod tidy ;; \
				*) \
					echo "Skipping Go dependency updates." ;; \
			esac; \
		else \
			echo "govulncheck failed (exit $$status)."; \
			exit $$status; \
		fi; \
	else \
		echo "Go source directory not found; skipping Go vulnerability remediation."; \
	fi

stack-up:
	cd $(GO_ROOT) && PYTHONPATH=$(shell pwd) LINUX_RAG_SOCKET=/tmp/linux-rag/rag-service.sock \
	go run ./cmd/ragman-admin run --config $(shell pwd)/configs/test.yaml --wait-ready

stack-down:
	cd infra && podman-compose down --remove-orphans --timeout 30

