from __future__ import annotations

from datetime import date

import pytest

from sales_pipeline.aggregate import (
    DaySummary,
    build_daily_report,
    category_summary,
    daily_summary,
    product_summary,
)
from sales_pipeline.loader import clean_sales, load_sales


def test_daily_summary(clean_df):
    daily = daily_summary(clean_df)
    assert daily["date"].tolist() == [date(2026, 11, 1), date(2026, 11, 2)]
    assert daily["sales"].tolist() == [4500.0, 7200.0]
    assert daily["orders"].tolist() == [2, 3]
    assert daily["quantity"].tolist() == [4, 6]
    assert daily["avg_order_value"].tolist() == [2250.0, 2400.0]


def test_product_summary_sorted_by_sales(clean_df):
    products = product_summary(clean_df, date(2026, 11, 2))
    assert products["product_name"].tolist() == ["マグ", "豆A", "豆B"]
    assert products["sales"].tolist() == [3000.0, 3000.0, 1200.0]
    assert products["category"].tolist() == ["雑貨", "コーヒー", "コーヒー"]


def test_product_summary_all_days(clean_df):
    products = product_summary(clean_df).set_index("product_name")
    assert products.loc["豆A", "sales"] == 6000.0
    assert products.loc["豆A", "orders"] == 3


def test_category_summary_with_share(clean_df):
    categories = category_summary(clean_df, date(2026, 11, 1)).set_index("category")
    assert categories.loc["コーヒー", "sales"] == 3000.0
    assert categories.loc["雑貨", "sales"] == 1500.0
    # A1 はコーヒーと雑貨の両方に含まれるので、それぞれ1件として数える
    assert categories.loc["コーヒー", "orders"] == 2
    assert categories.loc["雑貨", "orders"] == 1
    assert categories["share"].sum() == pytest.approx(1.0)
    assert categories.loc["コーヒー", "share"] == pytest.approx(2 / 3)


def test_build_daily_report_defaults_to_latest_date(clean_df):
    report = build_daily_report(clean_df)
    assert report.target == DaySummary(date(2026, 11, 2), 7200.0, 3, 6)
    assert report.previous == DaySummary(date(2026, 11, 1), 4500.0, 2, 4)
    assert report.target.avg_order_value == 2400.0


def test_build_daily_report_first_day_has_no_previous(clean_df):
    report = build_daily_report(clean_df, date(2026, 11, 1))
    assert report.previous is None
    assert report.comparison_label == "前回比"


def test_comparison_label_for_consecutive_days(clean_df):
    assert build_daily_report(clean_df).comparison_label == "前日比"


def test_previous_is_latest_earlier_day_when_dates_have_gap(raw_frame):
    rows = [
        {"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "100"},
        {"order_id": "2", "date": "2026-11-05", "item": "豆", "qty": "1", "price": "100"},
        {"order_id": "3", "date": "2026-11-09", "item": "豆", "qty": "1", "price": "100"},
    ]
    report = build_daily_report(clean_sales(raw_frame(rows)).data, date(2026, 11, 9))
    assert report.previous.date == date(2026, 11, 5)
    assert report.comparison_label == "前回比"


def test_single_day_data(raw_frame):
    rows = [{"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "100"}]
    report = build_daily_report(clean_sales(raw_frame(rows)).data)
    assert report.previous is None
    assert len(report.daily) == 1


def test_zero_priced_items_are_counted(raw_frame):
    rows = [
        {"order_id": "1", "date": "2026-11-01", "item": "試供品", "qty": "1", "price": "0"},
        {"order_id": "2", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "100"},
    ]
    report = build_daily_report(clean_sales(raw_frame(rows)).data)
    assert report.target.orders == 2
    assert report.target.sales == 100.0


def test_build_daily_report_unknown_date(clean_df):
    with pytest.raises(ValueError, match="のデータがありません"):
        build_daily_report(clean_df, date(2026, 12, 31))


def test_build_daily_report_empty(clean_df):
    with pytest.raises(ValueError, match="0件"):
        build_daily_report(clean_df.iloc[0:0])


def test_day_summary_with_zero_orders():
    assert DaySummary(date(2026, 1, 1), 0.0, 0, 0).avg_order_value == 0.0


def test_sample_csv_totals(sample_csv):
    report = build_daily_report(load_sales(sample_csv).data)
    assert report.target.date == date(2026, 11, 18)
    assert report.target.sales == 32540.0
    assert report.target.orders == 9
    assert report.target.quantity == 25
    assert report.daily["sales"].tolist() == [19010.0, 21390.0, 32540.0]
    assert report.daily["orders"].tolist() == [7, 6, 9]
