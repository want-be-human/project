"""
Pipeline observability — stage-level tracking for the PCAP analysis pipeline.

Usage::

    from app.services.pipeline import PipelineTracker, PipelineStage

    tracker = PipelineTracker(pcap_id="...", db=db)
    with tracker.stage(PipelineStage.PARSE) as stg:
        result = parser.parse(...)
        stg.record_metrics({"flow_count": len(result)})
    run = tracker.finish()
"""

from app.services.pipeline.models import PipelineStage, StageRecord, PipelineRun
from app.services.pipeline.tracker import PipelineTracker

__all__ = [
    "PipelineStage",
    "StageRecord",
    "PipelineRun",
    "PipelineTracker",
]
