"""Create isolated, deterministic 1k/10k MySQL samples from UCI Online Retail II.

The source workbook is user-provided/downloaded separately. This script never
touches the configured application database; it writes only the two dedicated
retail_bench_* schemas and requires --apply before issuing DDL or inserts.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
import sys

import openpyxl
import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import get_settings


DATABASES = {1000: 'retail_bench_1k', 10000: 'retail_bench_10k'}
TABLE = 'retail_transaction'
BATCH_SIZE = 500
REQUIRED = {'invoiceno', 'stockcode', 'description', 'quantity', 'invoicedate',
            'unitprice', 'customerid', 'country'}


def sample_indices(total: int, count: int) -> list[int]:
    if count <= 0 or total < count:
        raise ValueError(f'need at least {count:,} valid rows; found {total:,}')
    if count == 1:
        return [0]
    return [(index * (total - 1)) // (count - 1) for index in range(count)]


def _clean_row(values: tuple, columns: dict[str, int]) -> tuple | None:
    def get(name):
        return values[columns[name]] if columns[name] < len(values) else None

    invoice, stock, description, quantity, date, price, customer, country = (
        get(name) for name in ('invoiceno', 'stockcode', 'description', 'quantity',
                               'invoicedate', 'unitprice', 'customerid', 'country'))
    if invoice is None or stock is None or date is None or country is None:
        return None
    try:
        quantity_value = int(quantity)
        price_value = Decimal(str(price or 0)).quantize(Decimal('0.0001'))
        if not price_value.is_finite():
            return None
    except (TypeError, ValueError, InvalidOperation):
        return None
    if isinstance(date, str):
        try:
            date = datetime.fromisoformat(date)
        except ValueError:
            return None
    if not isinstance(date, datetime):
        return None
    try:
        customer_value = int(customer) if customer is not None else None
    except (TypeError, ValueError):
        customer_value = None
    return (str(invoice)[:20], str(stock)[:20], str(description or '')[:255],
            quantity_value, date, price_value, customer_value, str(country)[:100])


def _iter_valid_rows(workbook_path: Path) -> Iterable[tuple]:
    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                continue
            columns = {str(value or '').strip().casefold().replace(' ', ''): index
                       for index, value in enumerate(header)}
            if 'invoiceno' not in columns and 'invoice' in columns:
                columns['invoiceno'] = columns['invoice']
            if 'unitprice' not in columns and 'price' in columns:
                columns['unitprice'] = columns['price']
            missing = REQUIRED - set(columns)
            if missing:
                raise ValueError(f"sheet '{sheet.title}' is missing columns: {', '.join(sorted(missing))}")
            for row in rows:
                cleaned = _clean_row(row, columns)
                if cleaned is not None:
                    yield cleaned
    finally:
        workbook.close()


def select_nested_samples(workbook_path: Path) -> tuple[list[tuple], list[tuple], int]:
    total = sum(1 for _ in _iter_valid_rows(workbook_path))
    indices_10k = set(sample_indices(total, 10000))
    selected_10k, selected_1k = [], []
    for index, row in enumerate(_iter_valid_rows(workbook_path)):
        if index in indices_10k:
            position = len(selected_10k)
            selected_10k.append(row)
            if position % 10 == 0 and len(selected_1k) < 1000:
                selected_1k.append(row)
    if len(selected_1k) != 1000 or len(selected_10k) != 10000:
        raise ValueError('the workbook changed between counting and sampling')
    return selected_1k, selected_10k, total


def _connect_without_database():
    settings = get_settings()
    if not settings.mysql_user:
        raise RuntimeError('configure a MySQL account with CREATE DATABASE and table write permissions')
    return pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password.get_secret_value(),
        charset='utf8mb4', connect_timeout=5, read_timeout=60, write_timeout=60,
        autocommit=False)


def _write_sample(connection, database: str, rows: list[tuple], *, replace: bool) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4')
        cursor.execute(f'USE `{database}`')
        cursor.execute('SHOW TABLES LIKE %s', (TABLE,))
        exists = cursor.fetchone() is not None
        if exists:
            cursor.execute(f'SELECT COUNT(*) FROM `{TABLE}`')
            nonempty = cursor.fetchone()[0] > 0
            if nonempty and not replace:
                raise RuntimeError(f'{database}.{TABLE} already has rows; pass --replace to rebuild this benchmark table')
            if replace:
                cursor.execute(f'DROP TABLE IF EXISTS `{TABLE}`')
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS `{TABLE}` (
            RowId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            InvoiceNo VARCHAR(20) NOT NULL,
            StockCode VARCHAR(20) NOT NULL,
            Description VARCHAR(255) NOT NULL,
            Quantity INT NOT NULL,
            InvoiceDate DATETIME NOT NULL,
            UnitPrice DECIMAL(12,4) NOT NULL,
            CustomerID INT NULL,
            Country VARCHAR(100) NOT NULL,
            INDEX idx_country (Country),
            INDEX idx_invoice_date (InvoiceDate),
            INDEX idx_stock_code (StockCode)
        ) ENGINE=InnoDB''')
        cursor.execute(f'SELECT COUNT(*) FROM `{TABLE}`')
        if cursor.fetchone()[0] > 0:
            return
        query = (f'INSERT INTO `{TABLE}` '
                 '(InvoiceNo,StockCode,Description,Quantity,InvoiceDate,UnitPrice,CustomerID,Country) '
                 'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)')
        for start in range(0, len(rows), BATCH_SIZE):
            cursor.executemany(query, rows[start:start + BATCH_SIZE])
        connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='path to UCI Online Retail II .xlsx workbook')
    parser.add_argument('--apply', action='store_true', help='create only retail_bench_1k and retail_bench_10k')
    parser.add_argument('--replace', action='store_true', help='drop/rebuild only the dedicated benchmark table')
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f'source workbook does not exist: {args.source}')
    sample_1k, sample_10k, total = select_nested_samples(args.source)
    report = {'dataset': 'UCI Online Retail II', 'source_rows': total,
              'selection': '10,000 evenly spaced valid rows; 1,000-row sample is every tenth selected row',
              'samples': {'retail_bench_1k': len(sample_1k), 'retail_bench_10k': len(sample_10k)},
              'source': 'https://doi.org/10.24432/C5CG6D', 'license': 'CC BY 4.0'}
    if not args.apply:
        report['mode'] = 'preview_only'
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print('No database connection or writes performed. Re-run with --apply using a dedicated MySQL setup account.')
        return 0
    if args.replace and not args.apply:
        parser.error('--replace requires --apply')
    connection = _connect_without_database()
    try:
        _write_sample(connection, DATABASES[1000], sample_1k, replace=args.replace)
        _write_sample(connection, DATABASES[10000], sample_10k, replace=args.replace)
    finally:
        connection.close()
    report['mode'] = 'applied'
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
