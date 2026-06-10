"""
Unit + integration tests for the Secure Notes API.
Uses FastAPI's TestClient so no live server is needed.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app, _notes

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_notes():
    """Reset in-memory store between tests for isolation."""
    _notes.clear()
    yield
    _notes.clear()


# ---------- Health ----------

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------- Create ----------

def test_create_note():
    resp = client.post("/notes", json={"title": "Hello", "body": "World"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Hello"
    assert data["body"] == "World"
    assert "id" in data


def test_create_note_missing_title():
    resp = client.post("/notes", json={"body": "No title here"})
    assert resp.status_code == 422


def test_create_note_empty_title():
    resp = client.post("/notes", json={"title": "", "body": "Empty title"})
    assert resp.status_code == 422


def test_create_note_title_too_long():
    resp = client.post("/notes", json={"title": "x" * 201, "body": "Too long title"})
    assert resp.status_code == 422


def test_create_note_body_too_long():
    resp = client.post("/notes", json={"title": "Ok", "body": "x" * 10_001})
    assert resp.status_code == 422


# ---------- Read ----------

def test_get_note():
    create = client.post("/notes", json={"title": "T", "body": "B"})
    note_id = create.json()["id"]
    resp = client.get(f"/notes/{note_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == note_id


def test_get_note_not_found():
    resp = client.get("/notes/nonexistent-id")
    assert resp.status_code == 404


def test_list_notes_empty():
    resp = client.get("/notes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_notes():
    client.post("/notes", json={"title": "A", "body": "a"})
    client.post("/notes", json={"title": "B", "body": "b"})
    resp = client.get("/notes")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------- Delete ----------

def test_delete_note():
    create = client.post("/notes", json={"title": "Del", "body": "me"})
    note_id = create.json()["id"]
    resp = client.delete(f"/notes/{note_id}")
    assert resp.status_code == 204
    assert client.get(f"/notes/{note_id}").status_code == 404


def test_delete_note_not_found():
    resp = client.delete("/notes/ghost-id")
    assert resp.status_code == 404
