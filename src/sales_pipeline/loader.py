"""売上CSVの読み込みと整形。

- 列名のゆれ（日本語/英語、大文字小文字、空白、全角）を正規の列名に寄せる
- 金額の「¥」「,」「円」や全角数字を取り除いて数値化する
- 日付の表記ゆれ（2026/11/16、2026年11月16日、時刻付き、タイムゾーン付き）を日付に揃える
- 文字列の前後空白・改行・連続空白を整える
- カテゴリの空欄は同じ商品の既知カテゴリで補い、不明なら「未分類」にする
- 整形できない行は捨て、理由ごとに件数を記録する

重複行の定義:
注文ID・日付・商品名・数量・単価がすべて同じ行は、二重出力とみなして2行目以降を除外する。
同じ注文で同じ商品を同数・同単価で2行に分けて記録する運用のデータには向かない。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

UNCATEGORIZED = "未分類"

# 正規の列名 → 受け付ける別名（比較は normalize_column_name 後の値で行う）
COLUMN_ALIASES: dict[str, list[str]] = {
    "order_id": ["order_id", "orderid", "order_no", "order_number", "注文id", "注文番号", "受注番号"],
    "order_date": ["order_date", "date", "ordered_at", "purchase_date", "注文日", "受注日", "日付", "注文日時"],
    "product_name": ["product_name", "product", "item", "item_name", "商品名", "商品"],
    "category": ["category", "カテゴリ", "カテゴリー", "分類", "商品カテゴリ"],
    "quantity": ["quantity", "qty", "数量", "個数"],
    "unit_price": ["unit_price", "price", "単価", "価格", "販売単価"],
    "amount": ["amount", "sales", "total", "subtotal", "売上", "売上金額", "金額", "小計"],
}

REQUIRED_COLUMNS = ["order_id", "order_date", "product_name", "quantity"]
OUTPUT_COLUMNS = ["order_id", "order_date", "product_name", "category", "quantity", "unit_price", "amount"]


@dataclass
class LoadResult:
    """整形済みデータと、整形の過程で何が起きたかの記録。"""

    data: pd.DataFrame
    rows_read: int
    dropped: dict[str, int] = field(default_factory=dict)
    filled_category: int = 0
    filled_category_from_product: int = 0
    column_mapping: dict[str, str] = field(default_factory=dict)

    @property
    def rows_kept(self) -> int:
        return len(self.data)

    @property
    def rows_dropped(self) -> int:
        return sum(self.dropped.values())


def normalize_column_name(name: str) -> str:
    """列名を比較用に正規化する（例: ' Order ID ' → 'order_id'）。"""
    text = unicodedata.normalize("NFKC", str(name)).strip().lower()
    return re.sub(r"[\s\-]+", "_", text)


_ALIAS_LOOKUP: dict[str, str] = {
    normalize_column_name(alias): canonical
    for canonical, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}


def resolve_columns(columns: list[str]) -> dict[str, str]:
    """元の列名 → 正規の列名 の対応表を作る。同じ正規名に当たる列は最初の1つだけ採用する。"""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for original in columns:
        canonical = _ALIAS_LOOKUP.get(normalize_column_name(original))
        if canonical and canonical not in used:
            mapping[original] = canonical
            used.add(canonical)
    return mapping


DUPLICATE_KEYS = ["order_id", "order_date", "product_name", "quantity", "unit_price"]

# 先頭の日付部分（2026/11/16・2026.11.16・2026年11月16日 など）。時刻の小数秒には触れない
_DATE_PART = re.compile(r"^(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:\s*日)?")

# 時刻の後ろに付くタイムゾーン表記（+09:00 / +0900 / Z）
_TZ_SUFFIX = re.compile(r"(\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)\s*(?:Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)


def _normalize_text(series: pd.Series) -> pd.Series:
    """NFKC正規化し、改行・タブ・連続空白を半角スペース1つにまとめて前後を削る。"""
    return (
        series.astype("string")
        .str.normalize("NFKC")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def to_number(series: pd.Series) -> pd.Series:
    """'¥1,200' や '１２００円' を 1200.0 にする。変換できない値は NaN。"""
    cleaned = _normalize_text(series).str.replace(r"[¥$,円\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def to_date(series: pd.Series) -> pd.Series:
    """表記ゆれのある日付文字列を日付（時刻0時）にする。変換できない値は NaT。

    タイムゾーン付きの日時（例: 2026-11-18T10:00:00+09:00）は、オフセットを外して
    表記どおりの現地日付で扱う。タイムゾーンの有無が混ざっていても落ちないようにするため。
    """
    text = (
        _normalize_text(series)
        .str.replace(_DATE_PART, r"\1-\2-\3", regex=True)
        .str.replace(_TZ_SUFFIX, r"\1", regex=True)
        .str.replace(r"(?<=\d)Z$", "", regex=True)
    )
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    return parsed.dt.normalize()


def read_csv_any_encoding(path: Path) -> pd.DataFrame:
    """UTF-8（BOM付き含む）で読めなければ Shift_JIS(cp932) で読む。"""
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return pd.read_csv(path, dtype="string", encoding=encoding, skipinitialspace=True)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError as exc:
            raise ValueError(f"CSVが空です（ヘッダー行もありません）: {path}") from exc
    raise ValueError(f"CSVの文字コードを判別できませんでした（UTF-8 / Shift_JIS 以外）: {path}")


def clean_sales(raw: pd.DataFrame) -> LoadResult:
    """生の売上データを整形して LoadResult を返す。"""
    mapping = resolve_columns(list(raw.columns))
    df = raw[list(mapping)].rename(columns=mapping).copy()

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if "unit_price" not in df.columns and "amount" not in df.columns:
        missing.append("unit_price または amount")
    if missing:
        raise ValueError(f"必須列が見つかりません: {', '.join(missing)}（読み取った列: {list(raw.columns)}）")

    rows_read = len(df)
    dropped: dict[str, int] = {}

    def drop(mask: pd.Series, reason: str) -> None:
        nonlocal df
        count = int(mask.sum())
        if count:
            dropped[reason] = dropped.get(reason, 0) + count
            df = df.loc[~mask].copy()

    # 全列が空の行（CSV末尾の空行など）
    drop(df.isna().all(axis=1), "空行")

    df["order_id"] = _normalize_text(df["order_id"])
    df["product_name"] = _normalize_text(df["product_name"])
    df["order_date"] = to_date(df["order_date"])
    df["quantity"] = to_number(df["quantity"])
    for col in ("unit_price", "amount"):
        df[col] = to_number(df[col]) if col in df.columns else pd.Series(float("nan"), index=df.index)

    if "category" in df.columns:
        df["category"] = _normalize_text(df["category"])
    else:
        df["category"] = pd.Series(pd.NA, index=df.index, dtype="string")

    drop(df["order_id"].isna() | (df["order_id"] == ""), "注文IDなし")
    drop(df["order_date"].isna(), "日付が不正")
    drop(df["product_name"].isna() | (df["product_name"] == ""), "商品名なし")
    qty = df["quantity"]
    drop(qty.isna() | (qty <= 0) | (qty % 1 != 0), "数量が不正")

    # 単価と金額は片方あれば補完する
    df["amount"] = df["amount"].fillna(df["quantity"] * df["unit_price"])
    df["unit_price"] = df["unit_price"].fillna(df["amount"] / df["quantity"])
    drop(df["amount"].isna() | (df["amount"] < 0) | (df["unit_price"] < 0), "金額が不正")
    drop(df.duplicated(subset=DUPLICATE_KEYS), "重複行")

    # カテゴリ空欄は、同じ商品の他の行で最も多いカテゴリで補完し、それでも不明なら「未分類」
    blank_category = df["category"].isna() | (df["category"] == "")
    known = df.loc[~blank_category]
    product_to_category = (
        known.groupby("product_name")["category"].agg(lambda s: s.value_counts().index[0]).to_dict()
    )
    # 1件も一致しないと map の結果が float になるため、文字列型に固定してから埋める
    inferred = df.loc[blank_category, "product_name"].map(product_to_category).astype("string")
    filled_from_product = int(inferred.notna().sum())
    df.loc[blank_category, "category"] = inferred.fillna(UNCATEGORIZED)
    filled_category = int(blank_category.sum())

    df["quantity"] = df["quantity"].astype("int64")
    df["category"] = df["category"].astype(str)
    df["product_name"] = df["product_name"].astype(str)
    df["order_id"] = df["order_id"].astype(str)
    df = df[OUTPUT_COLUMNS].sort_values(["order_date", "order_id"]).reset_index(drop=True)

    return LoadResult(
        data=df,
        rows_read=rows_read,
        dropped=dropped,
        filled_category=filled_category,
        filled_category_from_product=filled_from_product,
        column_mapping=mapping,
    )


def load_sales(path: str | Path) -> LoadResult:
    """CSVファイルを読み込んで整形する。"""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"入力CSVが見つかりません: {csv_path}")
    if not csv_path.is_file():
        raise ValueError(f"入力パスがファイルではありません: {csv_path}")
    return clean_sales(read_csv_any_encoding(csv_path))
