from sqlalchemy.exc import OperationalError, StatementError

from api.core.database import DATABASE_UNAVAILABLE_DETAIL, is_database_unavailable


def test_connection_failures_are_reported_as_temporarily_unavailable():
    error = OperationalError("SELECT 1", {}, ConnectionError("connection refused"))

    assert is_database_unavailable(error) is True
    assert "configuration" not in DATABASE_UNAVAILABLE_DETAIL.lower()
    assert "credentials" not in DATABASE_UNAVAILABLE_DETAIL.lower()


def test_database_value_errors_are_not_mislabeled_as_connection_failures():
    error = StatementError(
        "invalid input value for enum tree_status_enum",
        "INSERT INTO tree ...",
        {},
        ValueError("invalid enum value"),
    )

    assert is_database_unavailable(error) is False
