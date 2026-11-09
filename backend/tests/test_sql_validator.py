import pytest
from app.services.sql_validator import validate_sql
from app.core.errors import AppError

SCHEMA = [{'table': 'genre', 'columns': [{'name': 'GenreId'}, {'name': 'Name'}]}]
RETAIL_SCHEMA = [{'table': 'retail_transaction', 'columns': [
    {'name': 'InvoiceDate'}, {'name': 'Quantity'}, {'name': 'UnitPrice'},
]}]


def test_valid_select():
    sql, table = validate_sql('SELECT GenreId, Name FROM Genre', 'Genre', SCHEMA)
    assert sql == 'SELECT GenreId, Name FROM genre LIMIT 100'
    assert table == 'genre'


def test_limit_is_bounded():
    assert 'LIMIT 100' in validate_sql('SELECT * FROM genre LIMIT 10000', 'genre', SCHEMA)[0]


def test_aggregate():
    assert 'COUNT(*)' in validate_sql('SELECT COUNT(*) AS total FROM genre', 'genre', SCHEMA)[0]


def test_mysql_year_function_is_safe_for_known_date_column():
    sql, table = validate_sql(
        'SELECT COUNT(*) AS total FROM retail_transaction WHERE YEAR(InvoiceDate) = 2010',
        'retail_transaction', RETAIL_SCHEMA,
    )

    assert table == 'retail_transaction'
    assert 'YEAR(InvoiceDate) = 2010' in sql


def test_date_range_and_operator_is_safe_for_known_date_column():
    sql, _ = validate_sql(
        "SELECT COUNT(*) AS total FROM retail_transaction "
        "WHERE InvoiceDate >= '2010-01-01' AND InvoiceDate < '2011-01-01'",
        'retail_transaction', RETAIL_SCHEMA,
    )

    assert "InvoiceDate >= '2010-01-01'" in sql
    assert "InvoiceDate < '2011-01-01'" in sql


def test_or_predicate_is_safe_for_known_columns():
    sql, table = validate_sql(
        "SELECT Name FROM genre WHERE Name='Rock' OR Name='Jazz'",
        'genre', SCHEMA,
    )

    assert table == 'genre'
    assert "Name = 'Rock' OR Name = 'Jazz'" in sql


@pytest.mark.parametrize('sql', [
    'DELETE FROM genre', 'SELECT * FROM genre; DROP TABLE genre',
    'SELECT * FROM genre JOIN genre b ON 1=1', 'SELECT * FROM genre, genre b',
    'SELECT (SELECT Name FROM genre) FROM genre', 'SELECT * FROM mysql.user',
    'SELECT password FROM genre', 'SELECT SLEEP(5) FROM genre',
    "SELECT LOAD_FILE('/etc/passwd') FROM genre", "SELECT * INTO OUTFILE 'x' FROM genre",
    'SELECT * FROM genre FOR UPDATE', 'SELECT * FROM genre UNION SELECT * FROM genre',
    'WITH x AS (SELECT * FROM genre) SELECT * FROM x', 'SELECT * FROM genre -- comment',
    'SELECT @x:=Name FROM genre', 'SELECT * FROM genre LIMIT -1',
    'SELECT TS_OR_DS_TO_DATE(Name) FROM genre',
])
def test_unsafe_sql(sql):
    with pytest.raises(AppError):
        validate_sql(sql, 'genre', SCHEMA)
