from sqlalchemy import create_engine


def make_engine(url: str):
    return create_engine(
        url, pool_pre_ping=True, pool_size=5, max_overflow=0,
        pool_timeout=3, hide_parameters=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=3000"},
    )
