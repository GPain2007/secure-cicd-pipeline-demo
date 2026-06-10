"""
Secure Notes API - A minimal FastAPI application for managing personal notes.
Demonstrates security best practices: input validation, typed responses,
no secrets in code, structured logging.
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import logging
import uuid

# Structured logging — never log sensitive user data
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Secure Notes API",
    description="A minimal, security-conscious notes service used as a CI/CD pipeline demo.",
    version="1.0.0",
)

# In-memory store (intentionally simple — the focus is the pipeline, not the DB)
_notes: dict[str, dict] = {}


# ---------- Schemas ----------

class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=10_000)


class NoteResponse(BaseModel):
    id: str
    title: str
    body: str


# ---------- Routes ----------

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Liveness probe used by the pipeline smoke test."""
    return {"status": "ok"}


@app.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate):
    note_id = str(uuid.uuid4())
    _notes[note_id] = {"id": note_id, "title": payload.title, "body": payload.body}
    logger.info("Note created id=%s", note_id)
    return _notes[note_id]


@app.get("/notes/{note_id}", response_model=NoteResponse)
def get_note(note_id: str):
    note = _notes.get(note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@app.get("/notes", response_model=list[NoteResponse])
def list_notes():
    return list(_notes.values())


@app.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str):
    if note_id not in _notes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    del _notes[note_id]
    logger.info("Note deleted id=%s", note_id)
