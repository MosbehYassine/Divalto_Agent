import importlib.util
import unittest
from pathlib import Path


def _load_etl_module():
    repo_root = Path(__file__).resolve().parents[2]
    etl_path = repo_root / "mock database" / "load_mock_to_dw.py"
    spec = importlib.util.spec_from_file_location("load_mock_to_dw", etl_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


etl = _load_etl_module()


class TestEtlNormalization(unittest.TestCase):
    def test_normalize_source_rows_valid_minimal(self):
        customers = [(1, "Alice", "Paris")]
        products = [(101, "Laptop")]
        sales = [("2026-04-29", 1, 101, 2, 1000, "INV-1")]
        mapping = {}

        clean_customers, clean_products, clean_sales, report = etl.normalize_source_rows(
            customers, products, sales, mapping
        )

        self.assertEqual(len(clean_customers), 1)
        self.assertEqual(len(clean_products), 1)
        self.assertEqual(len(clean_sales), 1)
        self.assertEqual(report["sales_rejected"], 0)
        self.assertEqual(clean_sales[0][5], 2000.0)

    def test_normalize_source_rows_custom_index_map(self):
        customers = [("Paris", "Bob", "C-002")]
        products = [("CategoryA", "P-5", "Phone")]
        sales = [("INV-5", 99.5, 3, "P-5", "C-002", "29/04/2026", 298.5)]
        mapping = {
            "customers_index_map": {"city": 0, "customer_name": 1, "customer_code": 2},
            "products_index_map": {"category": 0, "product_code": 1, "product_name": 2},
            "sales_index_map": {
                "source_document_no": 0,
                "unit_price": 1,
                "quantity": 2,
                "product_code": 3,
                "customer_code": 4,
                "sale_date": 5,
                "amount": 6,
            },
        }

        clean_customers, clean_products, clean_sales, report = etl.normalize_source_rows(
            customers, products, sales, mapping
        )

        self.assertEqual(report["customers_rejected"], 0)
        self.assertEqual(report["products_rejected"], 0)
        self.assertEqual(report["sales_rejected"], 0)
        self.assertEqual(clean_customers[0][0], "C-002")
        self.assertEqual(clean_products[0][0], "P-5")
        self.assertEqual(clean_sales[0][6], "INV-5")
        self.assertEqual(clean_sales[0][5], 298.5)

    def test_normalize_source_rows_rejects_bad_sales(self):
        customers = [(1, "Alice", "Paris")]
        products = [(101, "Laptop")]
        sales = [("not-a-date", 1, 101, 2, 1000, "INV-1")]
        mapping = {}

        _, _, clean_sales, report = etl.normalize_source_rows(customers, products, sales, mapping)

        self.assertEqual(len(clean_sales), 0)
        self.assertEqual(report["sales_rejected"], 1)
        self.assertTrue(report["reject_samples"])

    def test_normalize_source_rows_column_map(self):
        customers = [("C-010", "Client X", "Lyon")]
        products = [("P-9", "Mouse")]
        sales = [("INV-9", "P-9", "C-010", "2026-04-29", "3", "45.5")]
        mapping = {
            "customers_column_map": {
                "customer_code": "code_client",
                "customer_name": "nom_client",
                "city": "ville",
            },
            "products_column_map": {
                "product_code": "code_article",
                "product_name": "libelle_article",
            },
            "sales_column_map": {
                "source_document_no": "numero_piece",
                "product_code": "code_article",
                "customer_code": "code_client",
                "sale_date": "date_piece",
                "quantity": "qte",
                "unit_price": "pu",
            },
        }
        source_columns = {
            "customers": ["code_client", "nom_client", "ville"],
            "products": ["code_article", "libelle_article"],
            "sales": ["numero_piece", "code_article", "code_client", "date_piece", "qte", "pu"],
        }

        clean_customers, clean_products, clean_sales, report = etl.normalize_source_rows(
            customers, products, sales, mapping, source_columns=source_columns
        )

        self.assertEqual(report["customers_rejected"], 0)
        self.assertEqual(report["products_rejected"], 0)
        self.assertEqual(report["sales_rejected"], 0)
        self.assertEqual(clean_customers[0][0], "C-010")
        self.assertEqual(clean_products[0][0], "P-9")
        self.assertEqual(clean_sales[0][6], "INV-9")
        self.assertEqual(clean_sales[0][5], 136.5)

    def test_validate_policy_strict_mode_raises_on_reject(self):
        report = {
            "customers_rejected": 0,
            "products_rejected": 0,
            "sales_rejected": 1,
            "sales_valid": 10,
        }
        with self.assertRaises(RuntimeError):
            etl.validate_normalization_policy(report, strict_mode=True)

    def test_validate_policy_raises_when_no_valid_sales(self):
        report = {
            "customers_rejected": 0,
            "products_rejected": 0,
            "sales_rejected": 0,
            "sales_valid": 0,
        }
        with self.assertRaises(RuntimeError):
            etl.validate_normalization_policy(report, strict_mode=False)


if __name__ == "__main__":
    unittest.main()
