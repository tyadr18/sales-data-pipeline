"""日次・商品別・カテゴリ別の集計。

指標の定義:
- 売上 (sales)            : 金額 (amount) の合計
- 注文件数 (orders)       : 注文IDのユニーク数
- 販売数量 (quantity)     : 数量の合計
- 平均単価 (avg_order_value): 売上 ÷ 注文件数（いわゆる客単価）

1つの注文に複数カテゴリの商品が含まれる場合、カテゴリ別・商品別の注文件数では
それぞれ1件として数えるため、内訳の注文件数の合計は全体の注文件数より多くなることがある。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

SUMMARY_COLUMNS = ["sales", "orders", "quantity", "avg_order_value"]


def _summarize(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    grouped = df.groupby(keys, sort=False).agg(
        sales=("amount", "sum"),
        orders=("order_id", "nunique"),
        quantity=("quantity", "sum"),
    )
    grouped["avg_order_value"] = grouped["sales"] / grouped["orders"]
    return grouped.reset_index()


def _filter_date(df: pd.DataFrame, target: date | None) -> pd.DataFrame:
    if target is None:
        return df
    return df.loc[df["order_date"].dt.date == target]


def daily_summary(df: pd.DataFrame) -> pd.DataFrame:
    """日付ごとの売上・注文件数・数量・平均単価（日付昇順）。"""
    result = _summarize(df.assign(date=df["order_date"].dt.date), ["date"])
    return result.sort_values("date").reset_index(drop=True)[["date", *SUMMARY_COLUMNS]]


def product_summary(df: pd.DataFrame, target: date | None = None) -> pd.DataFrame:
    """商品別の集計（売上降順、同額なら商品名順）。"""
    subset = _filter_date(df, target)
    result = _summarize(subset, ["category", "product_name"])
    result = result.sort_values(["sales", "product_name"], ascending=[False, True])
    return result.reset_index(drop=True)[["product_name", "category", *SUMMARY_COLUMNS]]


def category_summary(df: pd.DataFrame, target: date | None = None) -> pd.DataFrame:
    """カテゴリ別の集計（売上降順）。構成比 share（0〜1）付き。"""
    subset = _filter_date(df, target)
    result = _summarize(subset, ["category"])
    total = result["sales"].sum()
    result["share"] = result["sales"] / total if total else 0.0
    result = result.sort_values(["sales", "category"], ascending=[False, True])
    return result.reset_index(drop=True)[["category", *SUMMARY_COLUMNS, "share"]]


@dataclass(frozen=True)
class DaySummary:
    date: date
    sales: float
    orders: int
    quantity: int

    @property
    def avg_order_value(self) -> float:
        return self.sales / self.orders if self.orders else 0.0


@dataclass(frozen=True)
class DailyReport:
    """1日分のレポートに必要な集計結果一式。"""

    target: DaySummary
    previous: DaySummary | None
    products: pd.DataFrame
    categories: pd.DataFrame
    daily: pd.DataFrame

    @property
    def comparison_label(self) -> str:
        """比較相手が暦の前日なら「前日比」、間に空き日があれば「前回比」。"""
        if self.previous is not None and self.target.date - self.previous.date == timedelta(days=1):
            return "前日比"
        return "前回比"


def _to_day_summary(row: pd.Series) -> DaySummary:
    return DaySummary(
        date=row["date"],
        sales=float(row["sales"]),
        orders=int(row["orders"]),
        quantity=int(row["quantity"]),
    )


def build_daily_report(df: pd.DataFrame, target: date | None = None) -> DailyReport:
    """対象日（省略時はデータ内の最新日）のレポートを組み立てる。

    比較相手は「データ内で対象日の直前にある日」。暦の前日でないときは
    comparison_label が「前回比」になる。
    """
    if df.empty:
        raise ValueError("集計対象のデータが0件です")

    daily = daily_summary(df)
    available = list(daily["date"])
    target = target or available[-1]
    if target not in available:
        raise ValueError(f"{target} のデータがありません（データの期間: {available[0]} 〜 {available[-1]}）")

    position = available.index(target)
    previous = _to_day_summary(daily.iloc[position - 1]) if position > 0 else None

    return DailyReport(
        target=_to_day_summary(daily.iloc[position]),
        previous=previous,
        products=product_summary(df, target),
        categories=category_summary(df, target),
        daily=daily,
    )
