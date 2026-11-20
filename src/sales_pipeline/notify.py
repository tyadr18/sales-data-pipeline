"""Slack 通知用のテキスト生成。

このモジュールは通知文と送信用ペイロードを作るだけで、実際の送信は行わない。
Webhook URL は秘密情報なので、コードやリポジトリには書かず環境変数
SLACK_WEBHOOK_URL で受け取り、画面に出すときは mask_secret で伏せる。
"""

from __future__ import annotations

from sales_pipeline.aggregate import DailyReport
from sales_pipeline.report import NO_COMPARISON, format_change, format_money, previous_value

SLACK_TOP_N = 3


def escape_slack(text: str) -> str:
    """Slack の mrkdwn で制御文字として扱われる & < > をエスケープする。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_slack_message(report: DailyReport, top_n: int = SLACK_TOP_N, currency_label: str = "円") -> str:
    """Slack の mrkdwn 形式で日次サマリーの通知文を作る。"""
    t, p = report.target, report.previous
    label = report.comparison_label

    def with_change(value: str, metric: str) -> str:
        change = format_change(getattr(t, metric), previous_value(p, metric))
        return value if change == NO_COMPARISON else f"{value}（{label} {change}）"

    lines = [
        f"*:bar_chart: 日次売上レポート {t.date.isoformat()}*",
        "• 売上: " + with_change(format_money(t.sales, currency_label), "sales"),
        "• 注文件数: " + with_change(f"{t.orders:,}件", "orders"),
        "• 平均単価: " + with_change(format_money(t.avg_order_value, currency_label), "avg_order_value"),
    ]

    top = report.products.head(top_n)
    if not top.empty:
        lines += ["", f"*売上上位{len(top)}商品*"]
        lines += [
            f"{rank}. {escape_slack(row.product_name)}  {format_money(row.sales, currency_label)}（{row.quantity:,}点）"
            for rank, row in enumerate(top.itertuples(index=False), start=1)
        ]

    if not report.categories.empty:
        best = report.categories.iloc[0]
        lines += ["", f"最も売れたカテゴリ: {escape_slack(best['category'])}（構成比 {best['share'] * 100:.1f}%）"]

    return "\n".join(lines)


def build_slack_payload(text: str, channel: str | None = None) -> dict[str, str]:
    """Incoming Webhook に POST する JSON ペイロードの形を返す（送信はしない）。"""
    payload = {"text": text}
    if channel:
        payload["channel"] = channel
    return payload


def mask_secret(value: str | None, visible: int = 4) -> str:
    """秘密情報を末尾数文字だけ残して伏せる（ログ・画面表示用）。"""
    if not value:
        return "(未設定)"
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * 8 + value[-visible:]
