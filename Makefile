.DEFAULT_GOAL := help

PYTHON_DISTRIBUTION := uv run
PYTHON_DIRS := $(strip $(foreach dir,src/python tests/python,$(if $(wildcard $(dir)),$(dir),)))

.PHONY: help lint format typecheck test test-python test-go format-python lint-python typecheck-python

help:
	@printf "Available targets:\\n"
	@printf "  lint           Run ruff against Python sources\\n"
	@printf "  format         Format Python sources with black\\n"
	@printf "  typecheck      Type-check Python sources with mypy\\n"
	@printf "  test           Run all tests (pytest + go test)\\n"

lint: lint-python

lint-python:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) ruff check $(PYTHON_DIRS); \
	else \
		echo "No Python directories found; skipping ruff check."; \
	fi

format: format-python

format-python:
	@if [ -n "$(PYTHON_DIRS)" ]; then \
		$(PYTHON_DISTRIBUTION) black $(PYTHON_DIRS); \
	else \
		echo "No Python directories found; skipping black format."; \
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
	cd src/go && go test ./...
