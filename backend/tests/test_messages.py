"""Tests for message API."""
import pytest
from fastapi.testclient import TestClient
from app.core.database import init_db, get_session
from app.models.conversation import Conversation
from main import app

client = TestClient(app)


@pytest.fixture
def db_session():
    """Create test database session."""
    init_db()
    yield next(get_session())
    # TODO: Clean up test data


@pytest.fixture
def auth_token():
    """Get auth token for testing."""
    response = client.post(
        "/auth/login",
        data={"username": "dev", "password": "dev"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login():
    """Test authentication."""
    response = client.post(
        "/auth/login",
        data={"username": "dev", "password": "dev"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_create_message(auth_token):
    """Test message creation."""
    # First create a conversation
    conv_response = client.post(
        "/conversations",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"title": "Test Conversation"}
    )
    assert conv_response.status_code == 200
    conv_id = conv_response.json()["id"]
    
    # Create message
    response = client.post(
        f"/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"content": "Hello, world!", "role": "user"}
    )
    assert response.status_code == 200
    assert response.json()["content"] == "Hello, world!"


