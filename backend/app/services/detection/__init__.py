"""检测服务模块。"""

from app.services.detection.service import DetectionService
from app.services.detection.composite import CompositeDetectionService

__all__ = ["DetectionService", "CompositeDetectionService"]
