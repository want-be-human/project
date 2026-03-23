"""
NetTwin-SOC 的 Alembic 环境配置。
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 这是 Alembic 配置对象
config = context.config

# 解析配置文件中的 Python 日志设置。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入所有模型，确保都注册到 Base
from app.models.base import Base  # noqa: E402
from app.models import (  # noqa: E402, F401
    PcapFile,
    Flow,
    Alert,
    Investigation,
    Recommendation,
    TwinPlan,
    DryRun,
    Scenario,
    ScenarioRun,
    EvidenceChain,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """以“离线”模式执行迁移。

    该模式只使用 URL 配置上下文，不创建 Engine。
    因此即使没有可用 DBAPI，也可以生成迁移脚本输出。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite 变更使用批处理模式
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以“在线”模式执行迁移。

    该模式会创建 Engine，并将连接绑定到迁移上下文。
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 变更使用批处理模式
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
