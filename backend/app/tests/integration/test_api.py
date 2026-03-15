"""
API integration tests for health and pcaps endpoints.
"""

import pytest
from fastapi.testclient import TestClient
import struct

from app.main import app
from app.api.deps import engine
from app.models.base import Base


@pytest.fixture(scope="function")
def client():
    """Create a test client with clean database."""
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    with TestClient(app) as c:
        yield c
    
    # Clean up
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_pcap_content() -> bytes:
    """Generate minimal valid PCAP content."""
    # PCAP global header
    header = struct.pack(
        '<IHHIIII',
        0xA1B2C3D4,  # Magic number
        2,           # Version major
        4,           # Version minor
        0,           # Timezone
        0,           # Sigfigs
        65535,       # Snaplen
        1            # Link type (Ethernet)
    )
    
    # One minimal packet (just header, no data)
    ts_sec = 1706700000
    ts_usec = 0
    caplen = 0
    origlen = 0
    packet_header = struct.pack('<IIII', ts_sec, ts_usec, caplen, origlen)
    
    return header + packet_header


class TestHealthEndpoint:
    """Tests for GET /api/v1/health"""

    def test_health_returns_ok(self, client: TestClient):
        """Health endpoint should return ok status."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["data"]["status"] == "ok"
        assert data["error"] is None


class TestPcapsEndpoints:
    """Tests for /api/v1/pcaps/* endpoints"""

    def test_list_pcaps_empty(self, client: TestClient):
        """List pcaps should return empty list initially."""
        response = client.get("/api/v1/pcaps")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["data"] == []

    def test_upload_pcap_success(self, client: TestClient, sample_pcap_content: bytes):
        """Upload should accept valid PCAP file."""
        files = {"file": ("test.pcap", sample_pcap_content, "application/octet-stream")}
        response = client.post("/api/v1/pcaps/upload", files=files)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["data"]["version"] == "1.1"
        assert data["data"]["filename"] == "test.pcap"
        assert data["data"]["status"] == "uploaded"
        assert data["data"]["progress"] == 0
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_upload_pcap_invalid_extension(self, client: TestClient):
        """Upload should reject files without .pcap extension."""
        files = {"file": ("test.txt", b"not a pcap", "text/plain")}
        response = client.post("/api/v1/pcaps/upload", files=files)
        
        assert response.status_code == 415
        data = response.json()
        
        assert data["ok"] is False
        assert data["error"]["code"] == "UNSUPPORTED_MEDIA"

    def test_upload_pcap_invalid_content(self, client: TestClient):
        """Upload should reject files with invalid PCAP magic number."""
        files = {"file": ("test.pcap", b"invalid content", "application/octet-stream")}
        response = client.post("/api/v1/pcaps/upload", files=files)
        
        assert response.status_code == 415
        data = response.json()
        
        assert data["ok"] is False
        assert data["error"]["code"] == "UNSUPPORTED_MEDIA"

    def test_get_pcap_status(self, client: TestClient, sample_pcap_content: bytes):
        """Get status should return pcap details."""
        # Upload first
        files = {"file": ("test.pcap", sample_pcap_content, "application/octet-stream")}
        upload_response = client.post("/api/v1/pcaps/upload", files=files)
        pcap_id = upload_response.json()["data"]["id"]
        
        # Get status
        response = client.get(f"/api/v1/pcaps/{pcap_id}/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["data"]["id"] == pcap_id

    def test_get_pcap_status_not_found(self, client: TestClient):
        """Get status should return 404 for non-existent pcap."""
        response = client.get("/api/v1/pcaps/00000000-0000-0000-0000-000000000000/status")
        
        assert response.status_code == 404
        data = response.json()
        
        assert data["ok"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_process_pcap(self, client: TestClient, sample_pcap_content: bytes):
        """Process should accept the request and update status."""
        # Upload first
        files = {"file": ("test.pcap", sample_pcap_content, "application/octet-stream")}
        upload_response = client.post("/api/v1/pcaps/upload", files=files)
        pcap_id = upload_response.json()["data"]["id"]
        
        # Start processing
        response = client.post(
            f"/api/v1/pcaps/{pcap_id}/process",
            json={"mode": "flows_only", "window_sec": 60}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["data"]["accepted"] is True
        
        # Check status updated
        status_response = client.get(f"/api/v1/pcaps/{pcap_id}/status")
        assert status_response.json()["data"]["status"] == "processing"
