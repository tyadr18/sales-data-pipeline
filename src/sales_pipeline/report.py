"""日次レポートを Markdown / CSV として出力する。

Markdown の表は外部ライブラリ（tabulate など）を使わずに組み立てる。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sales_pipeline.aggregate import DailyReport, DaySummary
from sales_pipeline.loader import LoadResult

NO_COMPARISON = "—"


def format_money(value: float, label: str = "円") -> str:
    return f"{round(value):,}{label}"


def format_change(current: float, previous: float | None) -> str:
    """増減率を '+12.5%' の形にする。比較できないとき（前回なし・前回0）は '—'。"""
    if previous is None or previous == 0:
        return NO_COMPARISON
    rate = (current - previous) / previous * 100
    return f"{rate:+.1f}%"


def previous_value(previous: DaySummary | None, metric: str) -> float | None:
    """比較相手の日があればその指標値を、なければ None を返す。"""
    return None if previous is None else float(getattr(previous, metric))


def _escape_cell(value: object) -> str:
    """表のセルを壊す文字（| と改行）を無害化する。"""
    return str(value).replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def markdown_table(headers: list[str], rows: list[list[str]], align: list[str] | None = None) -> str:
    """Markdown の表を作る。align は 'left' / 'right' のリスト。"""
    align = align or ["left"] * len(headers)
    separators = ["---:" if a == "right" else ":---" for a in align]
    lines = [
        "| " + " | ".join(_escape_cell(h) for h in headers) + " |",
        "| " + " | ".join(separators) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _kpi_rows(target: DaySummary, previous: DaySummary | None, label: str) -> list[list[str]]:
    def change(metric: str) -> str:
        return format_change(getattr(target, metric), previous_value(previous, metric))

    return [
        ["売上", format_money(target.sales, label), change("sales")],
        ["注文件数", f"{target.orders:,}件", change("orders")],
        ["販売数量", f"{target.quantity:,}点", change("quantity")],
        ["平均単価", format_money(target.avg_order_value, label), change("avg_order_value")],
    ]


def render_markdown(
    report: DailyReport,
    load_result: LoadResult | None = None,
    top_n: int = 5,
    currency_label: str = "円",
) -> str:
    target = report.target
    label = report.comparison_label
    sections: list[str] = [f"# 日次売上レポート {target.date.isoformat()}"]

    if report.previous:
        compared = f"（{label}は {report.previous.date.isoformat()} との比較）"
    else:
        compared = "（比較できる過去のデータなし）"
    sections.append(
        "## サマリー\n\n"
        + markdown_table(
            ["指標", "値", label],
            _kpi_rows(target, report.previous, currency_label),
            ["left", "right", "right"],
        )
        + f"\n\n{compared}"
    )

    product_rows = [
        [
            str(rank),
            row.product_name,
            row.category,
            format_money(row.sales, currency_label),
            f"{row.orders:,}",
            f"{row.quantity:,}",
        ]
        for rank, row in enumerate(report.products.head(top_n).itertuples(index=False), start=1)
    ]
    sections.append(
        f"## 商品別 売上上位{top_n}\n\n"
        + markdown_table(
            ["順位", "商品名", "カテゴリ", "売上", "注文件数", "数量"],
            product_rows,
            ["right", "left", "left", "right", "right", "right"],
        )
    )

    category_rows = [
        [
            row.category,
            format_money(row.sales, currency_label),
            f"{row.share * 100:.1f}%",
            f"{row.orders:,}",
            format_money(row.avg_order_value, currency_label),
        ]
        for row in report.categories.itertuples(index=False)
    ]
    sections.append(
        "## カテゴリ別\n\n"
        + markdown_table(
            ["カテゴリ", "売上", "構成比", "注文件数", "平均単価"],
            category_rows,
            ["left", "right", "right", "right", "right"],
        )
    )

    daily_rows = [
        [
            row.date.isoformat(),
            format_money(row.sales, currency_label),
            f"{row.orders:,}",
            format_money(row.avg_order_value, currency_label),
        ]
        for row in report.daily.itertuples(index=False)
    ]
    sections.append(
        "## 日次推移\n\n"
        + markdown_table(["日付", "売上", "注文件数", "平均単価"], daily_rows, ["left", "right", "right", "right"])
    )

    if load_result is not None:
        lines = [
            f"- 読み込み行数: {load_result.rows_read}",
            f"- 集計対象行数: {load_result.rows_kept}",
            f"- 除外行数: {load_result.rows_dropped}",
        ]
        lines += [f"  - {reason}: {count}" for reason, count in load_result.dropped.items()]
        if load_result.filled_category:
            from_product = load_result.filled_category_from_product
            lines.append(
                f"- カテゴリ空欄の補完: {load_result.filled_category}"
                f"（同一商品のカテゴリから {from_product} / 未分類 {load_result.filled_category - from_product}）"
            )
        sections.append("## データ品質\n\n" + "\n".join(lines))

    sections.append("> 平均単価 = 売上 ÷ 注文件数。カテゴリ・商品をまたぐ注文は各内訳で1件ずつ数えます。")
    return "\n\n".join(sections) + "\n"


def _round_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("sales", "avg_order_value"):
        if col in out.columns:
            out[col] = out[col].round(0).astype("int64")
    if "share" in out.columns:
        out["share"] = out["share"].round(4)
    return out


def write_outputs(
    report: DailyReport,
    markdown: str,
    slack_text: str,
    output_dir: str | Path,
) -> dict[str, Path]:
    """レポート一式を output_dir/YYYY-MM-DD/ に書き出し、書き出したパスを返す。

    同じ日付のフォルダがあれば上書きする。CSV は Excel でも文字化けしないよう
    BOM 付き UTF-8 で出力する。
    """
    day_dir = Path(output_dir) / report.target.date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "markdown": day_dir / "report.md",
        "daily_csv": day_dir / "daily_summary.csv",
        "products_csv": day_dir / "products.csv",
        "categories_csv": day_dir / "categories.csv",
        "slack_text": day_dir / "slack_message.txt",
    }
    paths["markdown"].write_text(markdown, encoding="utf-8")
    _round_for_csv(report.daily).to_csv(paths["daily_csv"], index=False, encoding="utf-8-sig")
    _round_for_csv(report.products).to_csv(paths["products_csv"], index=False, encoding="utf-8-sig")
    _round_for_csv(report.categories).to_csv(paths["categories_csv"], index=False, encoding="utf-8-sig")
    paths["slack_text"].write_text(slack_text, encoding="utf-8")
    return paths
