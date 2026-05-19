import os
import re
import sqlite3
import json
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

import pyodbc


BASE_DIR = Path(__file__).resolve().parent


def _read_env_file(env_path: Path) -> None:
    """Minimal .env loader (no external dependency required)."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


_read_env_file(BASE_DIR / ".env")


def _must_be_sql_identifier(value: str, var_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(
            f"{var_name} must contain only letters, numbers, underscores: {value}"
        )
    return value


SQL_SERVER = os.getenv("ETL_SQL_SERVER", r"localhost\MSSQLS_YR")
STAGING_DB = _must_be_sql_identifier(
    os.getenv("ETL_STAGING_DB", "StagingDB"), "ETL_STAGING_DB"
)
DW_DB = _must_be_sql_identifier(
    os.getenv("ETL_DW_DB", "DataWarehouseDB"), "ETL_DW_DB"
)
SQL_DRIVER = os.getenv("ETL_SQL_DRIVER", "ODBC Driver 17 for SQL Server")
SOURCE_SYSTEM = os.getenv("ETL_SOURCE_SYSTEM", "MOCK")
DEFAULT_COUNTRY = os.getenv("ETL_DEFAULT_COUNTRY", "Unknown")
DEFAULT_CATEGORY = os.getenv("ETL_DEFAULT_CATEGORY", "General")
DEFAULT_CUSTOMER_NAME = os.getenv("ETL_DEFAULT_CUSTOMER_NAME", "Unknown")
DEFAULT_CITY = os.getenv("ETL_DEFAULT_CITY", "Unknown")
DEFAULT_PRODUCT_NAME = os.getenv("ETL_DEFAULT_PRODUCT_NAME", "Unknown")
DEFAULT_SOURCE_DOCUMENT_NO = os.getenv("ETL_DEFAULT_SOURCE_DOCUMENT_NO", "UNKNOWN_DOC")
SQLITE_DB_PATH = Path(os.getenv("ETL_SQLITE_DB_PATH", str(BASE_DIR / "magasin_mock.db")))
SOURCE_TYPE = os.getenv("ETL_SOURCE_TYPE", "sqlite").strip().lower()
SOURCE_SQL_SERVER = os.getenv("ETL_SOURCE_SQL_SERVER", SQL_SERVER)
SOURCE_SQL_DB = _must_be_sql_identifier(
    os.getenv("ETL_SOURCE_SQL_DB", "SourceDB"), "ETL_SOURCE_SQL_DB"
)
SOURCE_SQL_DRIVER = os.getenv("ETL_SOURCE_SQL_DRIVER", SQL_DRIVER)
SOURCE_SQL_TRUSTED = os.getenv("ETL_SOURCE_SQL_TRUSTED", "yes")
SOURCE_SQL_USER = os.getenv("ETL_SOURCE_SQL_USER", "")
SOURCE_SQL_PASSWORD = os.getenv("ETL_SOURCE_SQL_PASSWORD", "")
MAPPING_PATH = Path(
    os.getenv("ETL_MAPPING_PATH", str(BASE_DIR / "etl_mapping.mock.json"))
)
STRICT_MODE = os.getenv("ETL_STRICT_MODE", "false").strip().lower() in {"1", "true", "yes"}
MAX_REJECT_SAMPLES = int(os.getenv("ETL_MAX_REJECT_SAMPLES", "5"))
DATE_FORMATS = tuple(
    fmt.strip()
    for fmt in os.getenv("ETL_DATE_FORMATS", "%Y-%m-%d,%d/%m/%Y,%Y/%m/%d,%d-%m-%Y,%Y%m%d").split(",")
    if fmt.strip()
)


def get_sqlserver_conn(database: str) -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{SQL_DRIVER}}};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)


def get_source_sqlserver_conn() -> pyodbc.Connection:
    trusted = SOURCE_SQL_TRUSTED.lower() in {"yes", "true", "1"}
    auth_part = "Trusted_Connection=yes;" if trusted else f"UID={SOURCE_SQL_USER};PWD={SOURCE_SQL_PASSWORD};"
    conn_str = (
        f"DRIVER={{{SOURCE_SQL_DRIVER}}};"
        f"SERVER={SOURCE_SQL_SERVER};"
        f"DATABASE={SOURCE_SQL_DB};"
        f"{auth_part}"
    )
    return pyodbc.connect(conn_str)


def load_mapping(mapping_path: Path) -> dict:
    if not mapping_path.exists():
        raise FileNotFoundError(f"Mapping file not found: {mapping_path}")

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    required_queries = {"customers_query", "products_query", "sales_query"}
    missing = [q for q in required_queries if q not in mapping]
    if missing:
        raise ValueError(f"Mapping file missing keys: {', '.join(missing)}")
    for key in (
        "customers_index_map",
        "products_index_map",
        "sales_index_map",
        "customers_column_map",
        "products_column_map",
        "sales_column_map",
    ):
        if key in mapping and not isinstance(mapping[key], dict):
            raise ValueError(f"{key} must be a JSON object when provided.")
    return mapping


def _pick_index(index_map: dict, key: str, default_value: int) -> int:
    value = index_map.get(key, default_value)
    if not isinstance(value, int):
        raise ValueError(f"Index '{key}' must be an integer. Got: {value}")
    if value < 0:
        raise ValueError(f"Index '{key}' must be >= 0 when used. Got: {value}")
    return value


def _resolve_field_positions(required_fields: Sequence[str], index_map: dict, column_map: dict, source_columns: Sequence[str], defaults: dict) -> dict:
    source_lookup = {str(col).strip().lower(): idx for idx, col in enumerate(source_columns)}
    positions = {}
    for field in required_fields:
        if field in index_map:
            positions[field] = _pick_index(index_map, field, 0)
            continue
        if field in column_map:
            alias = str(column_map[field]).strip().lower()
            if alias not in source_lookup:
                raise ValueError(f"Column '{column_map[field]}' mapped for '{field}' not found in source columns {list(source_columns)}")
            positions[field] = source_lookup[alias]
            continue
        if field in defaults:
            positions[field] = defaults[field]
            continue
        positions[field] = _pick_index({}, field, 0)
    return positions


def _coerce_str(value, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _coerce_float(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        raise ValueError("numeric value is null")
    text = str(value).strip().replace(",", ".")
    if not text:
        raise ValueError("numeric value is empty")
    return float(text)


def _coerce_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError("date is null")
    text = str(value).strip()
    if not text:
        raise ValueError("date is empty")

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    # Handles values such as "2026-04-29 00:00:00"
    return datetime.fromisoformat(text).date()


def _normalize_customers(rows, positions: dict):
    idx_code = positions["customer_code"]
    idx_name = positions["customer_name"]
    idx_city = positions["city"]
    idx_country = positions.get("country", -1)

    clean_rows = []
    rejects = []
    for i, row in enumerate(rows):
        try:
            code = _coerce_str(row[idx_code])
            if not code:
                raise ValueError("missing customer_code")
            name = _coerce_str(row[idx_name], DEFAULT_CUSTOMER_NAME)
            city = _coerce_str(row[idx_city], DEFAULT_CITY)
            country = _coerce_str(row[idx_country], DEFAULT_COUNTRY) if idx_country >= 0 else DEFAULT_COUNTRY
            clean_rows.append((code, name, city, country, SOURCE_SYSTEM))
        except Exception as exc:
            if len(rejects) < MAX_REJECT_SAMPLES:
                rejects.append(f"customers row#{i}: {exc}")
    return clean_rows, rejects


def _normalize_products(rows, positions: dict):
    idx_code = positions["product_code"]
    idx_name = positions["product_name"]
    idx_category = positions.get("category", -1)

    clean_rows = []
    rejects = []
    for i, row in enumerate(rows):
        try:
            code = _coerce_str(row[idx_code])
            if not code:
                raise ValueError("missing product_code")
            name = _coerce_str(row[idx_name], DEFAULT_PRODUCT_NAME)
            category = _coerce_str(row[idx_category], DEFAULT_CATEGORY) if idx_category >= 0 else DEFAULT_CATEGORY
            clean_rows.append((code, name, category, SOURCE_SYSTEM))
        except Exception as exc:
            if len(rejects) < MAX_REJECT_SAMPLES:
                rejects.append(f"products row#{i}: {exc}")
    return clean_rows, rejects


def _normalize_sales(rows, positions: dict):
    idx_sale_date = positions["sale_date"]
    idx_customer_code = positions["customer_code"]
    idx_product_code = positions["product_code"]
    idx_quantity = positions["quantity"]
    idx_unit_price = positions["unit_price"]
    idx_source_document_no = positions["source_document_no"]
    idx_amount = positions.get("amount", -1)

    clean_rows = []
    rejects = []
    for i, row in enumerate(rows):
        try:
            sale_date = _coerce_date(row[idx_sale_date])
            customer_code = _coerce_str(row[idx_customer_code])
            product_code = _coerce_str(row[idx_product_code])
            quantity = _coerce_float(row[idx_quantity])
            unit_price = _coerce_float(row[idx_unit_price])
            if not customer_code or not product_code:
                raise ValueError("missing customer_code or product_code")
            amount = (
                _coerce_float(row[idx_amount]) if idx_amount >= 0 else round(quantity * unit_price, 2)
            )
            source_document_no = _coerce_str(row[idx_source_document_no], DEFAULT_SOURCE_DOCUMENT_NO)
            clean_rows.append(
                (
                    sale_date,
                    customer_code,
                    product_code,
                    quantity,
                    unit_price,
                    amount,
                    source_document_no,
                    SOURCE_SYSTEM,
                )
            )
        except Exception as exc:
            if len(rejects) < MAX_REJECT_SAMPLES:
                rejects.append(f"sales row#{i}: {exc}")
    return clean_rows, rejects


def normalize_source_rows(customers, products, sales, mapping: dict, source_columns: dict | None = None):
    source_columns = source_columns or {}

    customers_positions = _resolve_field_positions(
        required_fields=("customer_code", "customer_name", "city", "country"),
        index_map=mapping.get("customers_index_map", {}),
        column_map=mapping.get("customers_column_map", {}),
        source_columns=source_columns.get("customers", []),
        defaults={"customer_code": 0, "customer_name": 1, "city": 2, "country": -1},
    )
    products_positions = _resolve_field_positions(
        required_fields=("product_code", "product_name", "category"),
        index_map=mapping.get("products_index_map", {}),
        column_map=mapping.get("products_column_map", {}),
        source_columns=source_columns.get("products", []),
        defaults={"product_code": 0, "product_name": 1, "category": -1},
    )
    sales_positions = _resolve_field_positions(
        required_fields=("sale_date", "customer_code", "product_code", "quantity", "unit_price", "source_document_no", "amount"),
        index_map=mapping.get("sales_index_map", {}),
        column_map=mapping.get("sales_column_map", {}),
        source_columns=source_columns.get("sales", []),
        defaults={
            "sale_date": 0,
            "customer_code": 1,
            "product_code": 2,
            "quantity": 3,
            "unit_price": 4,
            "source_document_no": 5,
            "amount": -1,
        },
    )

    clean_customers, rejected_customers = _normalize_customers(customers, customers_positions)
    clean_products, rejected_products = _normalize_products(products, products_positions)
    clean_sales, rejected_sales = _normalize_sales(sales, sales_positions)

    report = {
        "customers_in": len(customers),
        "customers_valid": len(clean_customers),
        "customers_rejected": len(customers) - len(clean_customers),
        "products_in": len(products),
        "products_valid": len(clean_products),
        "products_rejected": len(products) - len(clean_products),
        "sales_in": len(sales),
        "sales_valid": len(clean_sales),
        "sales_rejected": len(sales) - len(clean_sales),
        "reject_samples": rejected_customers + rejected_products + rejected_sales,
    }
    return clean_customers, clean_products, clean_sales, report


def validate_normalization_policy(report: dict, strict_mode: bool) -> None:
    if strict_mode and (
        report["customers_rejected"] > 0
        or report["products_rejected"] > 0
        or report["sales_rejected"] > 0
    ):
        raise RuntimeError("ETL_STRICT_MODE=true and some rows were rejected.")
    if report["sales_valid"] <= 0:
        raise RuntimeError("No valid sales rows after normalization; ETL aborted.")


def _execute_and_fetch(cur, query: str):
    cur.execute(query)
    rows = cur.fetchall()
    cols = [desc[0] for desc in (cur.description or [])]
    return rows, cols


def extract_from_source(mapping: dict):
    if SOURCE_TYPE == "sqlite":
        if not SQLITE_DB_PATH.exists():
            raise FileNotFoundError(f"SQLite database not found: {SQLITE_DB_PATH}")
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
    elif SOURCE_TYPE == "sqlserver":
        conn = get_source_sqlserver_conn()
    else:
        raise ValueError(
            f"Unsupported ETL_SOURCE_TYPE '{SOURCE_TYPE}'. Supported: sqlite, sqlserver"
        )

    cur = conn.cursor()
    customers, customer_cols = _execute_and_fetch(cur, mapping["customers_query"])
    products, product_cols = _execute_and_fetch(cur, mapping["products_query"])
    sales, sales_cols = _execute_and_fetch(cur, mapping["sales_query"])
    conn.close()
    source_columns = {
        "customers": customer_cols,
        "products": product_cols,
        "sales": sales_cols,
    }
    return customers, products, sales, source_columns


def load_staging(customers, products, sales):
    conn = get_sqlserver_conn(STAGING_DB)
    cur = conn.cursor()

    cur.execute("TRUNCATE TABLE dbo.stg_sales")
    cur.execute("TRUNCATE TABLE dbo.stg_products")
    cur.execute("TRUNCATE TABLE dbo.stg_customers")

    cur.fast_executemany = True

    cur.executemany(
        """
        INSERT INTO dbo.stg_customers (customer_code, customer_name, city, country, source_system)
        VALUES (?, ?, ?, ?, ?)
        """,
        customers,
    )

    cur.executemany(
        """
        INSERT INTO dbo.stg_products (product_code, product_name, category, source_system)
        VALUES (?, ?, ?, ?)
        """,
        products,
    )

    cur.executemany(
        """
        INSERT INTO dbo.stg_sales
        (
            sale_date,
            customer_code,
            product_code,
            quantity,
            unit_price,
            amount,
            source_document_no,
            source_system
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sales,
    )

    conn.commit()
    conn.close()


def load_dimensions_and_fact():
    conn = get_sqlserver_conn(DW_DB)
    cur = conn.cursor()

    # Insert missing customers (Type 1 style for now)
    cur.execute(
        f"""
        INSERT INTO dbo.DimCustomer (CustomerCode, CustomerName, City, Country)
        SELECT DISTINCT
            s.customer_code,
            s.customer_name,
            s.city,
            s.country
        FROM [{STAGING_DB}].dbo.stg_customers s
        LEFT JOIN dbo.DimCustomer d
            ON d.CustomerCode = s.customer_code
           AND d.IsCurrent = 1
        WHERE d.CustomerKey IS NULL
        """
    )

    # Insert missing products (Type 1 style for now)
    cur.execute(
        f"""
        INSERT INTO dbo.DimProduct (ProductCode, ProductName, Category)
        SELECT DISTINCT
            s.product_code,
            s.product_name,
            s.category
        FROM [{STAGING_DB}].dbo.stg_products s
        LEFT JOIN dbo.DimProduct d
            ON d.ProductCode = s.product_code
           AND d.IsCurrent = 1
        WHERE d.ProductKey IS NULL
        """
    )

    # Demo mode: full refresh of fact table for deterministic reruns
    cur.execute("TRUNCATE TABLE dbo.FactSales")

    cur.execute(
        f"""
        INSERT INTO dbo.FactSales
        (
            DateKey,
            CustomerKey,
            ProductKey,
            Quantity,
            UnitPrice,
            Amount,
            SourceDocumentNo
        )
        SELECT
            CONVERT(INT, FORMAT(s.sale_date, 'yyyyMMdd')) AS DateKey,
            dc.CustomerKey,
            dp.ProductKey,
            s.quantity,
            s.unit_price,
            s.amount,
            s.source_document_no
        FROM [{STAGING_DB}].dbo.stg_sales s
        JOIN dbo.DimCustomer dc
          ON dc.CustomerCode = s.customer_code
         AND dc.IsCurrent = 1
        JOIN dbo.DimProduct dp
          ON dp.ProductCode = s.product_code
         AND dp.IsCurrent = 1
        """
    )

    conn.commit()
    conn.close()


def print_counts():
    conn = get_sqlserver_conn(DW_DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM dbo.DimCustomer")
    dim_customer = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dbo.DimProduct")
    dim_product = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dbo.FactSales")
    fact_sales = cur.fetchone()[0]

    conn.close()

    print("Load completed:")
    print(f"- DimCustomer: {dim_customer}")
    print(f"- DimProduct : {dim_product}")
    print(f"- FactSales  : {fact_sales}")


def main():
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Starting ETL...")
    print(f"SQL Server   : {SQL_SERVER}")
    print(f"Staging DB   : {STAGING_DB}")
    print(f"DW DB        : {DW_DB}")
    print(f"Source type  : {SOURCE_TYPE}")
    print(f"Mapping file : {MAPPING_PATH}")
    if SOURCE_TYPE == "sqlite":
        print(f"SQLite source: {SQLITE_DB_PATH}")
    else:
        print(f"Source SQL   : {SOURCE_SQL_SERVER} / {SOURCE_SQL_DB}")

    mapping = load_mapping(MAPPING_PATH)
    customers, products, sales, source_columns = extract_from_source(mapping)
    clean_customers, clean_products, clean_sales, report = normalize_source_rows(
        customers, products, sales, mapping, source_columns=source_columns
    )
    print(f"Source columns customers: {source_columns.get('customers', [])}")
    print(f"Source columns products : {source_columns.get('products', [])}")
    print(f"Source columns sales    : {source_columns.get('sales', [])}")
    print("Extracted rows:")
    print(f"- customers: {report['customers_in']} (valid={report['customers_valid']}, rejected={report['customers_rejected']})")
    print(f"- products : {report['products_in']} (valid={report['products_valid']}, rejected={report['products_rejected']})")
    print(f"- sales    : {report['sales_in']} (valid={report['sales_valid']}, rejected={report['sales_rejected']})")
    if report["reject_samples"]:
        print("Rejected row samples:")
        for sample in report["reject_samples"][:MAX_REJECT_SAMPLES]:
            print(f"  - {sample}")

    validate_normalization_policy(report, STRICT_MODE)

    load_staging(clean_customers, clean_products, clean_sales)
    load_dimensions_and_fact()
    print_counts()

    print(f"[{datetime.now().isoformat(timespec='seconds')}] ETL finished.")


if __name__ == "__main__":
    main()
