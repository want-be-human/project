"""
Contract compliance tests.
Validates that contract/samples/*.json match Pydantic schemas.
"""

import json
import pytest
from pathlib import Path


# Find contract samples directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SAMPLES_DIR = PROJECT_ROOT / "contract" / "samples"


REQUIRED_SAMPLES = [
    "flow.sample.json",
    "alert.sample.json",
    "graph.sample.json",
    "investigation.sample.json",
    "recommendation.sample.json",
    "actionplan.sample.json",
    "dryrun.sample.json",
    "evidencechain.sample.json",
    "scenario.sample.json",
    "scenario_run_result.sample.json",
]

# GraphResponse (DOC C C5.1) is a computed view, not a persisted object
# It doesn't have id/created_at fields
SAMPLES_WITHOUT_ID_CREATED_AT = ["graph.sample.json"]


class TestContractSamples:
    """Test that all contract samples exist and are valid JSON."""

    def test_samples_directory_exists(self):
        """Contract samples directory should exist."""
        assert SAMPLES_DIR.exists(), f"Samples directory not found: {SAMPLES_DIR}"

    @pytest.mark.parametrize("filename", REQUIRED_SAMPLES)
    def test_sample_file_exists(self, filename: str):
        """Each required sample file should exist."""
        file_path = SAMPLES_DIR / filename
        assert file_path.exists(), f"Sample file not found: {file_path}"

    @pytest.mark.parametrize("filename", REQUIRED_SAMPLES)
    def test_sample_is_valid_json(self, filename: str):
        """Each sample file should contain valid JSON."""
        file_path = SAMPLES_DIR / filename
        if not file_path.exists():
            pytest.skip(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)  # Will raise if invalid JSON
        
        assert isinstance(data, dict), f"Sample should be a JSON object: {filename}"

    @pytest.mark.parametrize("filename", REQUIRED_SAMPLES)
    def test_sample_has_version(self, filename: str):
        """Each sample should have version field set to 1.1."""
        file_path = SAMPLES_DIR / filename
        if not file_path.exists():
            pytest.skip(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert "version" in data, f"Missing 'version' field in {filename}"
        assert data["version"] == "1.1", f"Version should be '1.1' in {filename}"

    @pytest.mark.parametrize("filename", REQUIRED_SAMPLES)
    def test_sample_has_id(self, filename: str):
        """Each sample should have id field (except GraphResponse)."""
        if filename in SAMPLES_WITHOUT_ID_CREATED_AT:
            pytest.skip("GraphResponse doesn't have id field per DOC C C5.1")
        
        file_path = SAMPLES_DIR / filename
        if not file_path.exists():
            pytest.skip(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert "id" in data, f"Missing 'id' field in {filename}"

    @pytest.mark.parametrize("filename", REQUIRED_SAMPLES)
    def test_sample_has_created_at(self, filename: str):
        """Each sample should have created_at field in ISO8601 format (except GraphResponse)."""
        if filename in SAMPLES_WITHOUT_ID_CREATED_AT:
            pytest.skip("GraphResponse doesn't have created_at field per DOC C C5.1")
        
        file_path = SAMPLES_DIR / filename
        if not file_path.exists():
            pytest.skip(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert "created_at" in data, f"Missing 'created_at' field in {filename}"
        
        # Validate ISO8601 format
        from datetime import datetime
        try:
            datetime.strptime(data["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pytest.fail(f"Invalid timestamp format in {filename}: {data['created_at']}")
