from __future__ import annotations

from datetime import date

from sales_pipeline.aggregate import build_daily_report
from sales_pipeline.loader import clean_sales
from sales_pipeline.notify import build_slack_message, build_slack_payload, escape_slack, mask_secret


def test_slack_message_content(clean_df):
    text = build_slack_message(build_daily_report(clean_df), top_n=2)
    lines = text.splitlines()
    assert lines[0] == "*:bar_chart: 日次売上レポート 2026-11-02*"
    assert "• 売上: 7,200円（前日比 +60.0%）" in lines
    assert "• 注文件数: 3件（前日比 +50.0%）" in lines
    assert "*売上上位2商品*" in lines
    assert "1. マグ  3,000円（2点）" in lines
    assert "最も売れたカテゴリ: コーヒー（構成比 58.3%）" in lines


def test_slack_message_without_previous_day(clean_df):
    text = build_slack_message(build_daily_report(clean_df, date(2026, 11, 1)))
    assert "• 売上: 4,500円" in text.splitlines()
    assert "前日比" not in text


def test_slack_message_escapes_control_characters(raw_frame):
    rows = [{"order_id": "1", "date": "2026-11-01", "item": "豆&ミル <限定>", "category": "A&B", "qty": "1", "price": "100"}]
    text = build_slack_message(build_daily_report(clean_sales(raw_frame(rows)).data))
    assert "1. 豆&amp;ミル &lt;限定&gt;  100円（1点）" in text
    assert "最も売れたカテゴリ: A&amp;B" in text
    assert "<限定>" not in text


def test_slack_message_uses_previous_label_when_dates_have_gap(raw_frame):
    rows = [
        {"order_id": "1", "date": "2026-11-01", "item": "豆", "qty": "1", "price": "1000"},
        {"order_id": "2", "date": "2026-11-03", "item": "豆", "qty": "1", "price": "1500"},
    ]
    text = build_slack_message(build_daily_report(clean_sales(raw_frame(rows)).data))
    assert "• 売上: 1,500円（前回比 +50.0%）" in text.splitlines()


def test_escape_slack():
    assert escape_slack("a & b <c>") == "a &amp; b &lt;c&gt;"


def test_slack_payload():
    assert build_slack_payload("hello") == {"text": "hello"}
    assert build_slack_payload("hello", "#sales") == {"text": "hello", "channel": "#sales"}


def test_mask_secret_hides_webhook_url():
    url = "https://hooks.slack.com/services/T000/B000/XXXXabcd"
    masked = mask_secret(url)
    assert masked == "********abcd"
    assert "hooks.slack.com" not in masked
    assert mask_secret(None) == "(未設定)"
    assert mask_secret("abc") == "***"
