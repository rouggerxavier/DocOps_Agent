"""Multi-tenancy isolation tests.

Validates that user data (documents, artifacts, retrieval, BM25, Chroma)
is fully isolated between users â€” no cross-tenant leakage.
"""

import shutil
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from docops.api.app import app
from docops.auth.dependencies import get_current_user
from docops.db.database import get_db
from docops.db.database import Base
from docops.db.models import User, DocumentRecord, ArtifactRecord
from docops.db import crud


# â”€â”€ Fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class FakeEmbeddings:
    """Deterministic fake embeddings for testing without API calls."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 10) / 10.0] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 8


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def user_a(db_session):
    return crud.create_user(db_session, "Alice", "alice@test.com", "hash_a")


@pytest.fixture
def user_b(db_session):
    return crud.create_user(db_session, "Bob", "bob@test.com", "hash_b")


@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def api_client_with_users():
    """API client with isolated in-memory DB and two authenticated users."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_auth_override = app.dependency_overrides.get(get_current_user)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    with TestSession() as db:
        user_a_db = crud.create_user(db, "Alice API", "alice.api@test.com", "hash_a")
        user_b_db = crud.create_user(db, "Bob API", "bob.api@test.com", "hash_b")
        user_a = SimpleNamespace(
            id=int(user_a_db.id),
            name=str(user_a_db.name),
            email=str(user_a_db.email),
            is_active=True,
        )
        user_b = SimpleNamespace(
            id=int(user_b_db.id),
            name=str(user_b_db.name),
            email=str(user_b_db.email),
            is_active=True,
        )

    def set_current_user(user):
        app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)

    try:
        yield client, TestSession, user_a, user_b, set_current_user
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

        if previous_auth_override is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_auth_override


def _make_chunk(text: str, file_name: str, user_id: int) -> Document:
    return Document(
        page_content=text,
        metadata={
            "chunk_id": str(uuid.uuid4()),
            "file_name": file_name,
            "source": f"docs/{file_name}",
            "page": "N/A",
            "user_id": user_id,
        },
    )


def _mock_config(tmpdir):
    """Create a mock config pointing to tmpdir."""
    mock = MagicMock()
    mock.chroma_dir = tmpdir / "chroma"
    mock.bm25_dir = tmpdir / "bm25"
    mock.docs_dir = tmpdir / "docs"
    mock.artifacts_dir = tmpdir / "artifacts"
    mock.gemini_api_key = "fake-key"
    mock.ingest_incremental = False
    mock.chunk_size = 500
    mock.chunk_overlap = 50
    mock.top_k = 6
    mock.retrieval_mode = "similarity"
    mock.min_relevance_score = 0.0
    mock.structured_chunking = False
    return mock


# â”€â”€ Test 1: User A cannot see User B's documents â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_user_a_cannot_see_user_b_docs(db_session, user_a, user_b):
    """Documents registered by user A are not visible to user B."""
    crud.create_document_record(
        db_session,
        user_id=user_a.id,
        doc_id="doc_a_1",
        file_name="alice_manual.pdf",
        source_path="/docs/alice_manual.pdf",
        storage_path="/docs/alice_manual.pdf",
        file_type="pdf",
        chunk_count=5,
    )
    crud.create_document_record(
        db_session,
        user_id=user_b.id,
        doc_id="doc_b_1",
        file_name="bob_guide.pdf",
        source_path="/docs/bob_guide.pdf",
        storage_path="/docs/bob_guide.pdf",
        file_type="pdf",
        chunk_count=3,
    )

    docs_a = crud.list_documents_for_user(db_session, user_a.id)
    docs_b = crud.list_documents_for_user(db_session, user_b.id)

    assert len(docs_a) == 1
    assert docs_a[0].file_name == "alice_manual.pdf"

    assert len(docs_b) == 1
    assert docs_b[0].file_name == "bob_guide.pdf"

    # Cross-check: A cannot find B's doc
    assert crud.get_document_by_user_and_file_name(db_session, user_a.id, "bob_guide.pdf") is None
    assert crud.get_document_by_user_and_file_name(db_session, user_b.id, "alice_manual.pdf") is None


# â”€â”€ Test 2: User A cannot summarize User B's doc â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_user_a_cannot_summarize_user_b_doc(api_client_with_users):
    """Route-level ownership check: summarize cannot access other tenant docs."""
    client, Session, user_a, user_b, set_current_user = api_client_with_users

    with Session() as db:
        crud.create_document_record(
            db,
            user_id=user_b.id,
            doc_id="doc_b_summary_only",
            file_name="bob_only.pdf",
            source_path="/uploads/user_2/bob_only.pdf",
            storage_path="/uploads/user_2/bob_only.pdf",
            file_type="pdf",
            chunk_count=2,
        )

    set_current_user(user_a)
    response = client.post(
        "/api/summarize",
        json={"doc": "bob_only.pdf", "save": False, "summary_mode": "brief"},
    )
    assert response.status_code == 404


def test_user_a_cannot_compare_with_user_b_doc(api_client_with_users):
    """Route-level ownership check: compare rejects cross-tenant refs."""
    client, Session, user_a, user_b, set_current_user = api_client_with_users

    with Session() as db:
        crud.create_document_record(
            db,
            user_id=user_a.id,
            doc_id="doc_a_compare",
            file_name="alice_doc.pdf",
            source_path="/uploads/user_1/alice_doc.pdf",
            storage_path="/uploads/user_1/alice_doc.pdf",
            file_type="pdf",
            chunk_count=4,
        )
        crud.create_document_record(
            db,
            user_id=user_b.id,
            doc_id="doc_b_compare",
            file_name="bob_doc.pdf",
            source_path="/uploads/user_2/bob_doc.pdf",
            storage_path="/uploads/user_2/bob_doc.pdf",
            file_type="pdf",
            chunk_count=5,
        )

    set_current_user(user_a)
    response = client.post(
        "/api/compare",
        json={"doc1": "alice_doc.pdf", "doc2": "bob_doc.pdf", "save": False},
    )
    assert response.status_code == 404


def test_user_a_cannot_access_user_b_doc(db_session, user_a, user_b):
    """Ownership check rejects docs belonging to another user."""
    from docops.services.ownership import require_user_document
    from fastapi import HTTPException

    crud.create_document_record(
        db_session,
        user_id=user_b.id,
        doc_id="doc_b_only",
        file_name="secret.pdf",
        source_path="/docs/secret.pdf",
        storage_path="/docs/secret.pdf",
        file_type="pdf",
    )

    # User A trying to access B's doc should fail
    with pytest.raises(HTTPException) as exc_info:
        require_user_document(db_session, user_a.id, "secret.pdf")
    assert exc_info.value.status_code == 404

    # User B can access their own doc
    doc = require_user_document(db_session, user_b.id, "secret.pdf")
    assert doc.file_name == "secret.pdf"


# â”€â”€ Test 3: Artifacts are isolated between users â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_user_a_artifacts_are_isolated(db_session, user_a, user_b):
    """Artifacts created by A are not visible to B."""
    crud.create_artifact_record(
        db_session,
        user_id=user_a.id,
        artifact_type="summary",
        filename="alice_summary.md",
        path="/artifacts/user_1/alice_summary.md",
    )
    crud.create_artifact_record(
        db_session,
        user_id=user_b.id,
        artifact_type="summary",
        filename="bob_summary.md",
        path="/artifacts/user_2/bob_summary.md",
    )

    a_artifacts = crud.list_artifacts_for_user(db_session, user_a.id)
    b_artifacts = crud.list_artifacts_for_user(db_session, user_b.id)

    assert len(a_artifacts) == 1
    assert a_artifacts[0].filename == "alice_summary.md"
    assert len(b_artifacts) == 1
    assert b_artifacts[0].filename == "bob_summary.md"


# â”€â”€ Test 4: Same filename different users â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_user_a_artifacts_are_isolated_via_api(api_client_with_users):
    """Route-level artifact listing only returns records from current_user."""
    client, Session, user_a, user_b, set_current_user = api_client_with_users

    with tempfile.TemporaryDirectory() as temp_dir:
        path_a = Path(temp_dir) / "a.md"
        path_b = Path(temp_dir) / "b.md"
        path_a.write_text("A artifact", encoding="utf-8")
        path_b.write_text("B artifact", encoding="utf-8")

        with Session() as db:
            crud.create_artifact_record(
                db,
                user_id=user_a.id,
                artifact_type="summary",
                filename="a.md",
                path=str(path_a),
            )
            crud.create_artifact_record(
                db,
                user_id=user_b.id,
                artifact_type="summary",
                filename="b.md",
                path=str(path_b),
            )

        set_current_user(user_a)
        response_a = client.get("/api/artifacts")
        assert response_a.status_code == 200
        assert [item["filename"] for item in response_a.json()] == ["a.md"]

        set_current_user(user_b)
        response_b = client.get("/api/artifacts")
        assert response_b.status_code == 200
        assert [item["filename"] for item in response_b.json()] == ["b.md"]

def test_same_filename_different_users(db_session, user_a, user_b):
    """Two users can upload a file with the same name without collision."""
    from docops.ingestion.metadata import build_doc_id

    doc_id_a = build_doc_id("docs/manual.pdf", user_id=user_a.id)
    doc_id_b = build_doc_id("docs/manual.pdf", user_id=user_b.id)

    # Different doc_ids even for the same path
    assert doc_id_a != doc_id_b

    crud.create_document_record(
        db_session,
        user_id=user_a.id,
        doc_id=doc_id_a,
        file_name="manual.pdf",
        source_path="docs/manual.pdf",
        storage_path=f"docs/user_{user_a.id}/manual.pdf",
        file_type="pdf",
        chunk_count=10,
    )
    crud.create_document_record(
        db_session,
        user_id=user_b.id,
        doc_id=doc_id_b,
        file_name="manual.pdf",
        source_path="docs/manual.pdf",
        storage_path=f"docs/user_{user_b.id}/manual.pdf",
        file_type="pdf",
        chunk_count=8,
    )

    doc_a = crud.get_document_by_user_and_file_name(db_session, user_a.id, "manual.pdf")
    doc_b = crud.get_document_by_user_and_file_name(db_session, user_b.id, "manual.pdf")

    assert doc_a is not None and doc_b is not None
    assert doc_a.doc_id != doc_b.doc_id
    assert doc_a.chunk_count == 10
    assert doc_b.chunk_count == 8


# â”€â”€ Test 5: Chroma collection per user â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_chroma_collection_per_user(tmpdir):
    """Each user gets a distinct Chroma collection."""
    from docops.ingestion.indexer import index_chunks_for_user, list_indexed_docs_for_user

    fake_emb = FakeEmbeddings()
    mock = _mock_config(tmpdir)

    chunks_a = [_make_chunk("Alice's content about AI.", "alice.txt", user_id=1)]
    chunks_b = [_make_chunk("Bob's content about databases.", "bob.txt", user_id=2)]

    with patch("docops.ingestion.indexer.config", mock), \
         patch("docops.storage.paths.config", mock):
        count_a = index_chunks_for_user(1, chunks_a, embeddings=fake_emb)
        count_b = index_chunks_for_user(2, chunks_b, embeddings=fake_emb)

        assert count_a == 1
        assert count_b == 1

        docs_a = list_indexed_docs_for_user(1, embeddings=fake_emb)
        docs_b = list_indexed_docs_for_user(2, embeddings=fake_emb)

    file_names_a = {d["file_name"] for d in docs_a}
    file_names_b = {d["file_name"] for d in docs_b}

    assert "alice.txt" in file_names_a
    assert "bob.txt" not in file_names_a

    assert "bob.txt" in file_names_b
    assert "alice.txt" not in file_names_b


# â”€â”€ Test 6: Retrieval is user-scoped â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_retrieval_is_user_scoped(tmpdir):
    """Retrieval for user A does not return chunks from user B."""
    from docops.ingestion.indexer import index_chunks_for_user, get_vectorstore_for_user

    fake_emb = FakeEmbeddings()
    mock = _mock_config(tmpdir)

    chunks_a = [
        _make_chunk("Python is a programming language.", "python.txt", user_id=1),
        _make_chunk("Python has dynamic typing.", "python.txt", user_id=1),
    ]
    chunks_b = [
        _make_chunk("Java is a compiled language.", "java.txt", user_id=2),
        _make_chunk("Java uses static typing.", "java.txt", user_id=2),
    ]

    with patch("docops.ingestion.indexer.config", mock), \
         patch("docops.storage.paths.config", mock):
        index_chunks_for_user(1, chunks_a, embeddings=fake_emb)
        index_chunks_for_user(2, chunks_b, embeddings=fake_emb)

        vs_a = get_vectorstore_for_user(1, embeddings=fake_emb)
        vs_b = get_vectorstore_for_user(2, embeddings=fake_emb)

        results_a = vs_a.similarity_search("programming", k=10)
        results_b = vs_b.similarity_search("programming", k=10)

    # User A's results should only contain their own file
    for doc in results_a:
        assert doc.metadata.get("file_name") != "java.txt", "User A retrieved User B's chunk!"

    # User B's results should only contain their own file
    for doc in results_b:
        assert doc.metadata.get("file_name") != "python.txt", "User B retrieved User A's chunk!"


# â”€â”€ Test 7: BM25 is user-scoped â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_bm25_is_user_scoped(tmpdir):
    """BM25 index for user A does not contain chunks from user B."""
    from docops.rag.hybrid import build_bm25_index_for_user, bm25_search_for_user

    mock = _mock_config(tmpdir)

    chunks_a = [_make_chunk("Alpha bravo charlie delta", "alpha.txt", user_id=1)]
    chunks_b = [_make_chunk("Echo foxtrot golf hotel", "echo.txt", user_id=2)]

    def _mock_bm25_dir(uid):
        d = tmpdir / "bm25" / f"user_{uid}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    with patch("docops.rag.hybrid.get_user_bm25_dir") as mock_dir:
        mock_dir.side_effect = _mock_bm25_dir

        build_bm25_index_for_user(1, chunks_a)
        build_bm25_index_for_user(2, chunks_b)

        results_a = bm25_search_for_user(1, "alpha bravo", k=5)
        results_b = bm25_search_for_user(2, "alpha bravo", k=5)

    # User A should find results; user B should not (different corpus)
    assert len(results_a) >= 1
    assert any("Alpha" in r.page_content for r in results_a)

    # User B searched for "alpha bravo" but only has "echo foxtrot" corpus
    for doc in results_b:
        assert "Alpha" not in doc.page_content, "BM25 leaked data from user A to user B!"


# â”€â”€ Test 8: Collection names are distinct â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_collection_names_distinct():
    """Chroma collection names are unique per user."""
    from docops.storage.paths import get_user_collection_name

    name_1 = get_user_collection_name(1)
    name_2 = get_user_collection_name(2)

    assert name_1 != name_2
    assert "1" in name_1
    assert "2" in name_2


# â”€â”€ Test 9: Chunk IDs include user_id â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_chunk_ids_include_user_id():
    """Chunks for the same content but different users get different IDs."""
    from docops.ingestion.metadata import build_chunk_id

    meta_a = {"source_path": "docs/file.txt", "page_start": 1, "page_end": 1,
              "section_path": "", "chunk_index": 0, "user_id": 1}
    meta_b = {**meta_a, "user_id": 2}

    id_a = build_chunk_id("same content", meta_a)
    id_b = build_chunk_id("same content", meta_b)

    assert id_a != id_b


# â”€â”€ Test 10: Doc IDs include user_id â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_doc_ids_include_user_id():
    """Doc IDs for the same path but different users are distinct."""
    from docops.ingestion.metadata import build_doc_id

    id_a = build_doc_id("docs/report.pdf", user_id=1)
    id_b = build_doc_id("docs/report.pdf", user_id=2)

    assert id_a != id_b


# â”€â”€ Test 11: Filesystem paths per user â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_filesystem_paths_per_user(tmpdir):
    """Upload, artifact and BM25 directories are unique per user."""
    mock = _mock_config(tmpdir)

    with patch("docops.storage.paths.config", mock):
        from docops.storage.paths import (
            get_user_upload_dir,
            get_user_artifacts_dir,
            get_user_bm25_dir,
        )

        upload_1 = get_user_upload_dir(1)
        upload_2 = get_user_upload_dir(2)

        assert upload_1 != upload_2
        assert upload_1.exists()
        assert upload_2.exists()

        artifacts_1 = get_user_artifacts_dir(1)
        artifacts_2 = get_user_artifacts_dir(2)
        assert artifacts_1 != artifacts_2

        bm25_1 = get_user_bm25_dir(1)
        bm25_2 = get_user_bm25_dir(2)
        assert bm25_1 != bm25_2


# â”€â”€ Test 12: CRUD document record upsert â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_document_record_upsert(db_session, user_a):
    """Creating a document with the same doc_id updates rather than duplicates."""
    rec1 = crud.create_document_record(
        db_session,
        user_id=user_a.id,
        doc_id="doc_x",
        file_name="report.pdf",
        source_path="/docs/report.pdf",
        storage_path="/docs/report.pdf",
        file_type="pdf",
        chunk_count=5,
    )

    rec2 = crud.create_document_record(
        db_session,
        user_id=user_a.id,
        doc_id="doc_x",
        file_name="report.pdf",
        source_path="/docs/report.pdf",
        storage_path="/docs/report.pdf",
        file_type="pdf",
        chunk_count=10,  # updated
    )

    assert rec1.id == rec2.id
    assert rec2.chunk_count == 10

    all_docs = crud.list_documents_for_user(db_session, user_a.id)
    assert len(all_docs) == 1
