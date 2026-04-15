"""
NetTwin-SOC 的 Alembic 环境配置。
从 app.core.config 动态读取 DATABASE_URL，支持 PostgreSQL
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Alembic配置对象
config = context.config

# 解析配置文件中的 Python 日志设置。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从应用配置动态注入 DATABASE_URL
from app.core.config import settings  # noqa: E402
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

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
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
