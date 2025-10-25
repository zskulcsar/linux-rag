"""Integration test validating WeaviateVectorStore against the real stack."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import pytest

from linux_rag.retrieval.providers import WeaviateVectorStore

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_DIR = REPO_ROOT / "infra"
STACK_DATA_ROOT = REPO_ROOT / ".tmp" / "integration-stack"
WEAVIATE_HTTP = "http://127.0.0.1:8080"
CLASS_NAME = "KnowledgeSource"

pytestmark = pytest.mark.integration


def _have_podman_compose() -> bool:
    return shutil.which("podman-compose") is not None


def _run_compose(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["podman-compose", *args],
        cwd=INFRA_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def _wait_for_ready(url: str, *, timeout: int = 180) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5):
                return
        except urllib.error.URLError:
            time.sleep(2)
    raise TimeoutError(f"Service at {url} did not become ready within {timeout} seconds.")


def _delete_existing_class() -> None:
    request = urllib.request.Request(
        f"{WEAVIATE_HTTP}/v1/schema/{CLASS_NAME}",
        method="DELETE",
    )
    try:
        urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise


def _create_class_schema() -> None:
    schema = {
        "class": CLASS_NAME,
        "description": "Integration test class for KnowledgeSource documents.",
        "vectorizer": "none",
        "properties": [
            {"name": "title", "dataType": ["text"]},
            {"name": "snippet", "dataType": ["text"]},
            {"name": "source_path", "dataType": ["text"]},
            {"name": "section", "dataType": ["text"]},
        ],
    }
    request = urllib.request.Request(
        f"{WEAVIATE_HTTP}/v1/schema",
        data=json.dumps(schema).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=10)


def _insert_document(vector: list[float]) -> dict[str, str]:
    document_id = str(uuid4())
    payload = {
        "class": CLASS_NAME,
        "id": document_id,
        "properties": {
            "title": "mount(8)",
            "snippet": "Mount filesystems defined in /etc/fstab.",
            "source_path": "/usr/share/man/man8/mount.8",
            "section": "8",
        },
        "vector": vector,
    }
    request = urllib.request.Request(
        f"{WEAVIATE_HTTP}/v1/objects",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=10)
    return payload["properties"]


@pytest.fixture(scope="module")
def running_stack():
    if not _have_podman_compose():
        pytest.skip("podman-compose is required for this test.")

    shutil.rmtree(STACK_DATA_ROOT, ignore_errors=True)
    STACK_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["LINUX_RAG_DATA_ROOT"] = str(STACK_DATA_ROOT)

    up = _run_compose(["up", "-d"], env)
    if up.returncode != 0:
        pytest.skip(f"Unable to start stack via podman-compose: {up.stderr}")

    try:
        _wait_for_ready(f"{WEAVIATE_HTTP}/v1/.well-known/ready")
        yield env
    finally:
        _run_compose(["down", "--remove-orphans", "--timeout", "30"], env)


@pytest.mark.asyncio
async def test_weaviate_vector_store_returns_ingested_document(running_stack) -> None:
    vector = [0.25, 0.5, 0.75]
    _delete_existing_class()
    _create_class_schema()
    properties = _insert_document(vector)

    store = WeaviateVectorStore(
        scheme="http",
        host="127.0.0.1",
        port=8080,
        grpc_port=50051,
        class_name=CLASS_NAME,
        properties=("title", "snippet", "source_path", "section"),
    )

    results = await store.query(vector, limit=3)
    assert results, "WeaviateVectorStore must return the ingested document."

    first = results[0]
    assert first["title"] == properties["title"]
    assert first["source_path"] == properties["source_path"]
    assert first["snippet"] == properties["snippet"]
    assert first["metadata"]["section"] == properties["section"]
    assert first["score"] > 0
