import pytest


def test_hello_world():
    assert "Hello, World!" == "Hello, World!"


def test_database_variable():
    try:
        from harmoniq import DB_PATH
    except ImportError:
        pytest.fail("DB_PATH pas trouver dans harmoniq/__init__.py")


def test_database_connection():
    from harmoniq.db.engine import engine
    try:
        with engine.connect() as conn:
            assert not conn.closed
    except Exception as e:
        pytest.fail(f"Could not connect to database: {e}")