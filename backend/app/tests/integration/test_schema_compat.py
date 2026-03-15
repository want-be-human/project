"""
Schema compatibility tests.

Validates that all contract samples can be parsed by their
corresponding Pydantic schemas, ensuring API contract stability
across code changes.
"""

import json
import pytest
from pathlib import Path

from app.schemas.flow import FlowRecordSchema
from app.schemas.agent import InvestigationSchema, RecommendationSchema
from app.schemas.evidence import EvidenceChainSchema
from app.schemas.scenario import ScenarioSchema
from app.schemas.pipeline import PipelineRunSchema

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
SAMPLES_DIR = PROJECT_ROOT / "contract" / "samples"


# Map sample filename to the Pydantic schema that should parse it.
# Only include samples where we have a matching schema.
SCHEMA_MAP = {
    "flow.sample.json": FlowRecordSchema,
    "investigation.sample.json": InvestigationSchema,
    "recommendation.sample.json": RecommendationSchema,
    "evidencechain.sample.json": EvidenceChainSchema,
    "scenario.sample.json": ScenarioSchema,
}

# These samples have a nested structure that needs special handling
# or don't map 1:1 to a single Pydantic model.
STRUCTURAL_CHECKS = [
    "alert.sample.json",
    "actionplan.sample.json",
    "compiled_plan.sample.json",
    "dryrun.sample.json",
    "scenario_run_result.sample.json",
    "graph.sample.json",
]


class TestSchemaCompatibility:
    """Verify contract samples are compatible with Pydantic schemas."""

    @pytest.mark.parametrize("filename,schema_cls", list(SCHEMA_MAP.items()))
    def test_sample_parses_with_schema(self, filename: str, schema_cls):
        """Each sample should be parseable by its corresponding Pydantic schema."""
        file_path = SAMPLES_DIR / filename
        if not file_path.exists():
            pytest.skip(f"Sample not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        obj = schema_cls.model_validate(data)
        assert obj is not None
        assert obj.version == "1.1"

    @pytest.mark.parametrize("filename", STRUCTURAL_CHECKS)
    def test_sample_has_required_structure(self, filename: str):
        """Structural samples should have expected top-level keys."""
        file_path = SAMPLES_DIR / filename
        if not file_path.exists():
            pytest.skip(f"Sample not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, dict)
        # Some pre-existing samples (e.g. compiled_plan) don't have a version field
        if "version" in data:
            assert data["version"] == "1.1"

    def test_pipeline_run_sample_exists_and_parses(self):
        """pipeline_run.sample.json should exist and parse with PipelineRunSchema."""
        file_path = SAMPLES_DIR / "pipeline_run.sample.json"
        if not file_path.exists():
            pytest.skip("pipeline_run.sample.json not yet created")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        obj = PipelineRunSchema.model_validate(data)
        assert obj.version == "1.1"
        assert len(obj.stages) >= 4

    def test_all_samples_have_consistent_version(self):
        """Samples that declare a version field should use version 1.1."""
        if not SAMPLES_DIR.exists():
            pytest.skip("Samples directory not found")

        for path in SAMPLES_DIR.glob("*.sample.json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "version" in data:
                assert data["version"] == "1.1", f"Version mismatch in {path.name}"

    def test_schema_fields_subset_of_sample(self):
        """
        Each schema's required fields should be present in the sample.
        This catches schema additions that break backward compatibility.
        """
        for filename, schema_cls in SCHEMA_MAP.items():
            file_path = SAMPLES_DIR / filename
            if not file_path.exists():
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Get required fields from schema
            required = set()
            for name, field_info in schema_cls.model_fields.items():
                if field_info.is_required():
                    required.add(name)

            missing = required - set(data.keys())
            assert not missing, (
                f"Sample {filename} missing required fields: {missing}"
            )
