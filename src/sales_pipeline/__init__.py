"""EC売上CSVを整形・集計し、日次レポートとSlack通知文を生成するパイプライン。"""

from sales_pipeline.aggregate import (
    DailyReport,
    DaySummary,
    build_daily_report,
    category_summary,
    daily_summary,
    product_summary,
)
from sales_pipeline.config import Config, load_config
from sales_pipeline.loader import LoadResult, clean_sales, load_sales
from sales_pipeline.notify import build_slack_message, build_slack_payload
from sales_pipeline.report import render_markdown, write_outputs

__all__ = [
    "Config",
    "DailyReport",
    "DaySummary",
    "LoadResult",
    "build_daily_report",
    "build_slack_message",
    "build_slack_payload",
    "category_summary",
    "clean_sales",
    "daily_summary",
    "load_config",
    "load_sales",
    "product_summary",
    "render_markdown",
    "write_outputs",
]

__version__ = "0.1.0"
