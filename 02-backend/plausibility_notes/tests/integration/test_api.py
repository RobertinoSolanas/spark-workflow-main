import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.db.database import get_db_session
from src.models.schemas.plausibility_notes import PlausibilityCheckResult


@pytest_asyncio.fixture
async def client(db_session):
    """Create an async client with database dependency override."""
    # Override the dependency to use the session from conftest
    app.dependency_overrides[get_db_session] = lambda: db_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def mock_results_data():
    return {
        "contradictions": [
            {
                "id": str(uuid.uuid4()),
                "description": "Desc 1",
                "status": "OPEN",
                "occurrences": [
                    {
                        "documentId": "doc1",
                        "documentName": "Doc 1",
                        "contentExcerpt": "Excerpt 1",
                        "pageNumber": 1,
                    }
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_job_done_endpoint(client, mock_results_data):
    """Test the job-done endpoint and subsequent retrieval."""
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    # Mock the service function that fetches external file
    with patch(
        "src.services.plausibility_notes_service.fetch_results_file"
    ) as mock_fetch:
        mock_fetch.return_value = PlausibilityCheckResult.model_validate(
            mock_results_data
        )

        response = await client.post(
            f"/plausibility-notes/{project_id}/job-done",
            json={"fileId": str(file_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "contradictions_found"
        assert data["contradictions_found"] == 1
        assert data["total_occurrences"] == 1
        assert data["previous_records_deleted"] == 0

        # Verify data via GET endpoint
        response = await client.get(f"/plausibility-notes/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["contradictions"]) == 1

        assert data["contradictions"][0]["occurrences"][0]["documentName"] == "Doc 1"


@pytest.mark.asyncio
async def test_get_notes_empty(client):
    """Test retrieving notes when none exist."""
    project_id = uuid.uuid4()
    response = await client.get(f"/plausibility-notes/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["contradictions"]) == 0


@pytest.mark.asyncio
async def test_update_note_status(client, mock_results_data):
    """Test updating the status of a plausibility note."""
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()
    note_id = mock_results_data["contradictions"][0]["id"]

    with patch(
        "src.services.plausibility_notes_service.fetch_results_file"
    ) as mock_fetch:
        mock_fetch.return_value = PlausibilityCheckResult.model_validate(
            mock_results_data
        )
        await client.post(
            f"/plausibility-notes/{project_id}/job-done",
            json={"fileId": str(file_id)},
        )

    response = await client.patch(
        f"/plausibility-notes/notes/{note_id}",
        json={"status": "RESOLVED"},
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # Verify the status was updated
    response = await client.get(f"/plausibility-notes/{project_id}")
    assert response.json()["contradictions"][0]["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_update_note_not_found(client):
    """Test updating a non-existent note returns 404."""
    note_id = uuid.uuid4()
    response = await client.patch(
        f"/plausibility-notes/notes/{note_id}",
        json={"status": "RESOLVED"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_note(client, mock_results_data):
    """Test deleting a plausibility note."""
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()
    note_id = mock_results_data["contradictions"][0]["id"]

    with patch(
        "src.services.plausibility_notes_service.fetch_results_file"
    ) as mock_fetch:
        mock_fetch.return_value = PlausibilityCheckResult.model_validate(
            mock_results_data
        )
        await client.post(
            f"/plausibility-notes/{project_id}/job-done",
            json={"fileId": str(file_id)},
        )

    response = await client.delete(f"/plausibility-notes/notes/{note_id}")
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # Verify the note was deleted
    response = await client.get(f"/plausibility-notes/{project_id}")
    assert len(response.json()["contradictions"]) == 0


@pytest.mark.asyncio
async def test_delete_note_not_found(client):
    """Test deleting a non-existent note returns 404."""
    note_id = uuid.uuid4()
    response = await client.delete(f"/plausibility-notes/notes/{note_id}")
    assert response.status_code == 404
