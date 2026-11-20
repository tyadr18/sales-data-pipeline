from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from sales_pipeline.aggregate import DaySummary, build_daily_report
from sales_pipeline.loader import clean_sales, load_sales
from sales_pipeline.report import (
    format_change,
    format_money,
    markdown_table,
    previous_value,
    render_markdown,
    write_outputs,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1234567, "1,234,567円"), (2400.4, "2,400円"), (2400.6, "2,401円"), (0, "0円")],
)
def test_format_money(value, expected):
    assert format_money(value) == expected


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [(120, 100, "+20.0%"), (80, 100, "-20.0%"), (100, 100, "+0.0%"), (100, None, "—"), (100, 0, "—")],
)
def test_format_change(current, previous, expected):
    assert format_change(current, previous) == expected


def test_markdown_table_alignment_and_escape():
    table = markdown_table(["名前", "値"], [["a|b", "1"]], ["left", "right"])
    assert table.splitlines() == [
        "| 名前 | 値 |",
        "| :--- | ---: |",
        "| a\\|b | 1 |",
    ]


def test_render_markdown_contains_sections(clean_df):
    report = build_daily_report(clean_df)
    md = render_markdown(report, top_n=2)
    assert md.startswith("# 日次売上レポート 2026-11-02")
    for heading in ("## サマリー", "## 商品別 売上上位2", "## カテゴリ別", "## 日次推移"):
        assert heading in md
    assert "| 売上 | 7,200円 | +60.0% |" in md
    assert "| 平均単価 | 2,400円 | +6.7% |" in md
    assert "豆B" not in md.split("## カテゴリ別")[0]  # 上位2件に絞られている
    assert "## データ品質" not in md


def test_render_markdown_with_load_stats(sample_csv):
    load_result = load_sales(sample_csv)
    md = render_markdown(build_daily_report(load_result.data), load_result)
    assert "## データ品質" in md
    assert "- 除外行数: 4" in md
    assert "同一商品のカテゴリから 2" in md


def test_render_markdown_without_previous(clean_df):
    md = render_markdown(build_daily_report(clean_df, date(2026, 11, 1)))
    assert "比較できる過去のデータなし" in md
    assert "| 売上 | 4,500円 | — |" in md


def test_render_markdown_uses_previous_label_when_dates_have_gap(raw_frame):
    rows = [
        {"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "1000"},
        {"order_id": "2", "date": "2026-11-04", "item": "豆", "qty": "2", "price": "1000"},
    ]
    md = render_markdown(build_daily_report(clean_sales(raw_frame(rows)).data))
    assert "| 指標 | 値 | 前回比 |" in md
    assert "（前回比は 2026-11-01 との比較）" in md
    assert "| 売上 | 2,000円 | +100.0% |" in md


def test_previous_value():
    assert previous_value(None, "sales") is None
    assert previous_value(DaySummary(date(2026, 1, 1), 0.0, 0, 0), "sales") == 0.0


def test_markdown_table_neutralizes_newlines():
    table = markdown_table(["名前"], [["1行目\n2行目\r\n3行目"]])
    assert table.splitlines()[-1] == "| 1行目 2行目 3行目 |"


def test_render_markdown_top_n_larger_than_products(clean_df):
    md = render_markdown(build_daily_report(clean_df), top_n=50)
    product_section = md.split("## 商品別 売上上位50")[1].split("## カテゴリ別")[0]
    assert product_section.count("\n| ") == 2 + 3  # ヘッダー2行 + 商品3行


def test_write_outputs(tmp_path, clean_df):
    report = build_daily_report(clean_df)
    paths = write_outputs(report, "# md\n", "slack text", tmp_path)

    assert all(path.exists() for path in paths.values())
    assert paths["markdown"].parent == tmp_path / "2026-11-02"
    assert paths["slack_text"].read_text(encoding="utf-8") == "slack text"

    products = pd.read_csv(paths["products_csv"], encoding="utf-8-sig")
    assert list(products.columns) == ["product_name", "category", "sales", "orders", "quantity", "avg_order_value"]
    assert products["sales"].dtype == "int64"

    daily = pd.read_csv(paths["daily_csv"], encoding="utf-8-sig")
    assert daily["sales"].tolist() == [4500, 7200]

    # Excel で文字化けしないよう BOM 付き
    assert paths["categories_csv"].read_bytes().startswith(b"\xef\xbb\xbf")


def test_write_outputs_overwrites_same_day(tmp_path, clean_df):
    report = build_daily_report(clean_df)
    write_outputs(report, "old", "old", tmp_path)
    paths = write_outputs(report, "new", "new", tmp_path)
    assert paths["markdown"].read_text(encoding="utf-8") == "new"
