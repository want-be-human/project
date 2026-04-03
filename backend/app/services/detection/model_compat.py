"""Helpers for validating persisted model compatibility."""

from app.core.logging import get_logger

logger = get_logger(__name__)


def validate_sklearn_version(meta: dict, model_label: str) -> bool:
    """
    Require an exact sklearn version match for persisted model loading.

    Pickled sklearn models are not forward-compatible across arbitrary versions,
    so we fail closed instead of trying to load them with warnings.
    """
    trained_version = meta.get("sklearn_version")
    if not trained_version:
        logger.warning(
            "%s metadata missing sklearn_version; refusing persisted load", model_label
        )
        return False

    try:
        import sklearn
    except ImportError:
        logger.warning("%s requires scikit-learn at runtime", model_label)
        return False

    current_version = sklearn.__version__
    if trained_version != current_version:
        logger.warning(
            "%s sklearn version mismatch: trained=%s, current=%s; refusing persisted load",
            model_label,
            trained_version,
            current_version,
        )
        return False

    return True
