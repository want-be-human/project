"""持久化模型兼容性校验辅助函数。"""

from app.core.logging import get_logger

logger = get_logger(__name__)


def validate_sklearn_version(meta: dict, model_label: str) -> bool:
    """
    要求加载持久化模型时 sklearn 版本精确匹配。

    经 pickle 序列化的 sklearn 模型在不同版本间不具备前向兼容性，
    因此选择拒绝加载而非带警告尝试加载。
    """
    trained_version = meta.get("sklearn_version")
    if not trained_version:
        logger.warning(
            "%s 元数据缺少 sklearn_version; 拒绝加载持久化模型", model_label
        )
        return False

    try:
        import sklearn
    except ImportError:
        logger.warning("%s 运行时需要 scikit-learn", model_label)
        return False

    current_version = sklearn.__version__
    if trained_version != current_version:
        logger.warning(
            "%s sklearn 版本不匹配: 训练时=%s, 当前=%s; 拒绝加载持久化模型",
            model_label,
            trained_version,
            current_version,
        )
        return False

    return True
