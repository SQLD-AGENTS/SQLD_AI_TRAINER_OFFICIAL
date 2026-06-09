import os
import pathlib
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# backend/ 를 sys.path 에 추가해 api 패키지 임포트 가능하게 함
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# 저장소 루트 .env 로드 (DATABASE_URL 등)
load_dotenv(pathlib.Path(__file__).resolve().parent.parent.parent / ".env")

from api.database import Base, DATABASE_URL  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL 을 환경변수에서 읽어 alembic.ini 의 placeholder 를 덮어씀
config.set_main_option("sqlalchemy.url", DATABASE_URL)

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
