from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from sales_pipeline.loader import (
    UNCATEGORIZED,
    clean_sales,
    load_sales,
    normalize_column_name,
    resolve_columns,
    to_date,
    to_number,
)


class TestColumnNames:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(" Order ID ", "order_id"), ("unit-price", "unit_price"), ("ＱＴＹ", "qty"), ("注文ID", "注文id")],
    )
    def test_normalize_column_name(self, raw, expected):
        assert normalize_column_name(raw) == expected

    def test_resolve_columns_maps_japanese_and_english_aliases(self):
        mapping = resolve_columns(["注文番号", "Date", "商品名", "カテゴリー", "Qty", "単価", "memo"])
        assert mapping == {
            "注文番号": "order_id",
            "Date": "order_date",
            "商品名": "product_name",
            "カテゴリー": "category",
            "Qty": "quantity",
            "単価": "unit_price",
        }

    def test_first_column_wins_when_aliases_collide(self):
        mapping = resolve_columns(["price", "単価"])
        assert mapping == {"price": "unit_price"}


class TestValueConversion:
    def test_to_number_strips_currency_and_fullwidth(self):
        series = pd.Series(["¥1,280", "１,３８０円", "￥2,480", " 980 ", "", "abc", None], dtype="string")
        result = to_number(series)
        assert result.iloc[:4].tolist() == [1280.0, 1380.0, 2480.0, 980.0]
        assert result.iloc[4:].isna().all()

    def test_to_date_handles_mixed_timezones(self):
        series = pd.Series(
            ["2026-11-01T23:30:00+09:00", "2026-11-02 10:00", "2026-11-03T01:00:00Z", "2026-11-04 08:00:00.123+0900"],
            dtype="string",
        )
        result = to_date(series)
        # オフセットは外し、表記どおりの現地日付で扱う
        assert [d.date() for d in result] == [
            date(2026, 11, 1),
            date(2026, 11, 2),
            date(2026, 11, 3),
            date(2026, 11, 4),
        ]

    def test_to_date_accepts_various_formats(self):
        series = pd.Series(
            [
                "2026/11/16",
                "2026年11月17日",
                "2026-11-18 14:05",
                "2026.11.19",
                "2026/1/5",
                "2026年11月20日 09:30",
                "2026-11-21 08:00:00.250",
                "不明",
                "2026-13-01",
                "",
            ],
            dtype="string",
        )
        result = to_date(series)
        assert [d.date() if pd.notna(d) else None for d in result] == [
            date(2026, 11, 16),
            date(2026, 11, 17),
            date(2026, 11, 18),
            date(2026, 11, 19),
            date(2026, 1, 5),
            date(2026, 11, 20),
            date(2026, 11, 21),
            None,
            None,
            None,
        ]


class TestCleanSales:
    def test_invalid_rows_are_dropped_with_reasons(self, raw_frame):
        raw = raw_frame(
            [
                {"注文ID": "1", "注文日": "2026-11-01", "商品名": "豆", "数量": "1", "単価": "100"},
                {"注文ID": "2", "注文日": "bad", "商品名": "豆", "数量": "1", "単価": "100"},
                {"注文ID": "3", "注文日": "2026-11-01", "商品名": None, "数量": "1", "単価": "100"},
                {"注文ID": "4", "注文日": "2026-11-01", "商品名": "豆", "数量": "0", "単価": "100"},
                {"注文ID": "5", "注文日": "2026-11-01", "商品名": "豆", "数量": "1.5", "単価": "100"},
                {"注文ID": "6", "注文日": "2026-11-01", "商品名": "豆", "数量": "1", "単価": "-100"},
                {"注文ID": None, "注文日": "2026-11-01", "商品名": "豆", "数量": "1", "単価": "100"},
                {"注文ID": "1", "注文日": "2026-11-01", "商品名": "豆", "数量": "1", "単価": "100"},
                {"注文ID": None, "注文日": None, "商品名": None, "数量": None, "単価": None},
            ]
        )
        result = clean_sales(raw)

        assert result.rows_read == 9
        assert result.rows_kept == 1
        assert result.dropped == {
            "空行": 1,
            "注文IDなし": 1,
            "日付が不正": 1,
            "商品名なし": 1,
            "数量が不正": 2,
            "金額が不正": 1,
            "重複行": 1,
        }

    @pytest.mark.parametrize("quantity", ["0", "-1", "-3", "1.5", "", "abc"])
    def test_invalid_quantity_values(self, raw_frame, quantity):
        raw = raw_frame([{"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": quantity, "price": "100"}])
        result = clean_sales(raw)
        assert result.rows_kept == 0
        assert result.dropped == {"数量が不正": 1}

    def test_negative_amount_is_dropped(self, raw_frame):
        raw = raw_frame([{"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "金額": "-500"}])
        assert clean_sales(raw).dropped == {"金額が不正": 1}

    def test_missing_both_price_and_amount_values(self, raw_frame):
        raw = raw_frame([{"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": None, "amount": ""}])
        assert clean_sales(raw).dropped == {"金額が不正": 1}

    def test_duplicates_differing_only_in_category_are_merged(self, raw_frame):
        row = {"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "100"}
        raw = raw_frame([{**row, "category": "コーヒー"}, {**row, "category": None}])
        result = clean_sales(raw)
        assert result.rows_kept == 1
        assert result.dropped == {"重複行": 1}
        assert result.filled_category == 0  # 除外した行は補完件数に数えない

    def test_same_product_in_different_orders_is_not_duplicate(self, raw_frame):
        row = {"date": "2026-11-01", "item": "豆", "qty": "1", "price": "100"}
        raw = raw_frame([{**row, "order_id": "1"}, {**row, "order_id": "2"}])
        assert clean_sales(raw).rows_kept == 2

    def test_whitespace_and_newlines_in_text_are_normalized(self, raw_frame):
        raw = raw_frame(
            [
                {"order_id": " 1 ", "date": "2026-11-01", "item": "豆\nA  200g", "qty": "1", "price": "100"},
                {"order_id": "1", "date": "2026-11-01", "item": "豆 A 200g", "qty": "1", "price": "100"},
            ]
        )
        result = clean_sales(raw)
        assert result.data["product_name"].tolist() == ["豆 A 200g"]
        assert result.dropped == {"重複行": 1}

    def test_header_only_returns_empty_data(self, raw_frame):
        raw = pd.DataFrame(columns=["注文ID", "注文日", "商品名", "数量", "単価"], dtype="string")
        result = clean_sales(raw)
        assert result.rows_read == 0
        assert result.data.empty
        assert list(result.data.columns) == ["order_id", "order_date", "product_name", "category", "quantity", "unit_price", "amount"]

    def test_all_rows_invalid(self, raw_frame):
        raw = raw_frame([{"order_id": "1", "date": "bad", "item": "豆", "qty": "1", "price": "100"}])
        result = clean_sales(raw)
        assert result.data.empty
        assert result.rows_dropped == 1

    def test_amount_and_unit_price_complement_each_other(self, raw_frame):
        raw = raw_frame(
            [
                {"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "2", "price": "500", "amount": None},
                {"order_id": "2", "date": "2026-11-01", "item": "豆", "qty": "4", "price": None, "amount": "2,000"},
            ]
        )
        data = clean_sales(raw).data
        assert data["amount"].tolist() == [1000.0, 2000.0]
        assert data["unit_price"].tolist() == [500.0, 500.0]

    def test_amount_column_only_is_enough(self, raw_frame):
        raw = raw_frame([{"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "2", "売上": "1200"}])
        assert clean_sales(raw).data.loc[0, "unit_price"] == 600.0

    def test_blank_category_is_inferred_from_same_product(self, raw_frame):
        raw = raw_frame(
            [
                {"order_id": "1", "date": "2026-11-01", "item": "豆", "category": "コーヒー", "qty": "1", "price": "100"},
                {"order_id": "2", "date": "2026-11-01", "item": "豆", "category": "", "qty": "1", "price": "100"},
                {"order_id": "3", "date": "2026-11-01", "item": "謎の商品", "category": None, "qty": "1", "price": "100"},
            ]
        )
        result = clean_sales(raw)
        assert result.data["category"].tolist() == ["コーヒー", "コーヒー", UNCATEGORIZED]
        assert result.filled_category == 2
        assert result.filled_category_from_product == 1

    def test_missing_category_column_becomes_uncategorized(self, raw_frame):
        raw = raw_frame([{"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "100"}])
        assert clean_sales(raw).data["category"].tolist() == [UNCATEGORIZED]

    def test_output_types(self, raw_frame):
        raw = raw_frame([{"order_id": "1", "date": "2026/11/01 10:00", "item": "豆", "qty": "２", "price": "¥100"}])
        data = clean_sales(raw).data
        assert list(data.columns) == ["order_id", "order_date", "product_name", "category", "quantity", "unit_price", "amount"]
        assert data["quantity"].dtype == "int64"
        assert data.loc[0, "order_date"] == pd.Timestamp("2026-11-01")

    def test_missing_required_columns_raise(self, raw_frame):
        raw = raw_frame([{"商品名": "豆", "数量": "1"}])
        with pytest.raises(ValueError, match="必須列が見つかりません"):
            clean_sales(raw)


class TestLoadSales:
    def test_sample_csv(self, sample_csv):
        result = load_sales(sample_csv)
        assert result.rows_read == 34
        assert result.rows_kept == 30
        assert result.dropped == {"日付が不正": 1, "商品名なし": 1, "数量が不正": 1, "重複行": 1}
        assert UNCATEGORIZED not in set(result.data["category"])

    def test_shift_jis_csv(self, tmp_path):
        path = tmp_path / "sjis.csv"
        path.write_text("注文ID,注文日,商品名,数量,単価\n1,2026/11/01,コーヒー豆,1,1000\n", encoding="cp932")
        result = load_sales(path)
        assert result.data.loc[0, "product_name"] == "コーヒー豆"

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_sales(tmp_path / "nothing.csv")

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_bytes(b"")
        with pytest.raises(ValueError, match="CSVが空です"):
            load_sales(path)

    def test_header_only_file(self, tmp_path):
        path = tmp_path / "header.csv"
        path.write_text("注文ID,注文日,商品名,数量,単価\n", encoding="utf-8")
        assert load_sales(path).rows_read == 0

    def test_directory_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="ファイルではありません"):
            load_sales(tmp_path)

    def test_utf8_bom_header(self, tmp_path):
        path = tmp_path / "bom.csv"
        path.write_text("注文ID,注文日,商品名,数量,単価\n1,2026/11/01,豆,1,100\n", encoding="utf-8-sig")
        assert load_sales(path).column_mapping["注文ID"] == "order_id"
