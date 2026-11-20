from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sales_pipeline.loader import clean_sales

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_csv() -> Path:
    return PROJECT_ROOT / "data" / "sample_sales.csv"


@pytest.fixture
def raw_frame():
    """文字列だけの DataFrame を作るヘルパー（CSVを読んだ直後の状態を再現する）。"""

    def _make(rows: list[dict[str, str | None]]) -> pd.DataFrame:
        return pd.DataFrame(rows, dtype="string")

    return _make


@pytest.fixture
def clean_df(raw_frame) -> pd.DataFrame:
    """2日分・2カテゴリの小さな整形済みデータ。"""
    rows = [
        {"order_id": "A1", "order_date": "2026-11-01", "product_name": "豆A", "category": "コーヒー", "quantity": "2", "unit_price": "1000"},
        {"order_id": "A1", "order_date": "2026-11-01", "product_name": "マグ", "category": "雑貨", "quantity": "1", "unit_price": "1500"},
        {"order_id": "A2", "order_date": "2026-11-01", "product_name": "豆A", "category": "コーヒー", "quantity": "1", "unit_price": "1000"},
        {"order_id": "B1", "order_date": "2026-11-02", "product_name": "豆A", "category": "コーヒー", "quantity": "3", "unit_price": "1000"},
        {"order_id": "B2", "order_date": "2026-11-02", "product_name": "マグ", "category": "雑貨", "quantity": "2", "unit_price": "1500"},
        {"order_id": "B3", "order_date": "2026-11-02", "product_name": "豆B", "category": "コーヒー", "quantity": "1", "unit_price": "1200"},
    ]
    return clean_sales(raw_frame(rows)).data
