"""コマンドラインからパイプライン全体（読み込み → 集計 → 出力）を実行する。

終了コード:
    0: 成功
    1: 入力・設定・出力のエラー（メッセージを標準エラーに表示）
    2: コマンドライン引数の誤り（argparse が表示）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from sales_pipeline.aggregate import build_daily_report
from sales_pipeline.config import Config, load_config
from sales_pipeline.loader import load_sales
from sales_pipeline.notify import SLACK_TOP_N, build_slack_message, build_slack_payload, mask_secret
from sales_pipeline.report import render_markdown, write_outputs


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"日付は YYYY-MM-DD 形式で指定してください: {text}") from exc


def _make_console_safe() -> None:
    """表示できない文字があっても落ちないようにする。

    Windows でリダイレクト・パイプすると標準出力が cp932 や cp1252 になり、
    「•」などで UnicodeEncodeError が起きるため、表示できない文字は置き換える。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sales-pipeline",
        description="EC売上CSVを整形・集計し、日次レポート(Markdown/CSV)とSlack通知文を生成します。",
    )
    parser.add_argument("-i", "--input", type=Path, help="入力CSVのパス（既定: SALES_INPUT_PATH）")
    parser.add_argument("-o", "--output", type=Path, help="出力先ディレクトリ（既定: SALES_OUTPUT_DIR）")
    parser.add_argument("-d", "--date", type=_parse_date, help="対象日 YYYY-MM-DD（既定: データ内の最新日）")
    parser.add_argument("--top", type=int, help="商品ランキングの件数（既定: SALES_TOP_N）")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="読み込む .env ファイル")
    parser.add_argument("--print-payload", action="store_true", help="Slack送信用のJSONペイロードを表示する")
    return parser


def run(config: Config, target: date | None = None, print_payload: bool = False) -> dict[str, Path]:
    load_result = load_sales(config.input_path)
    report = build_daily_report(load_result.data, target)
    markdown = render_markdown(report, load_result, top_n=config.top_n, currency_label=config.currency_label)
    slack_text = build_slack_message(
        report, top_n=min(SLACK_TOP_N, config.top_n), currency_label=config.currency_label
    )
    paths = write_outputs(report, markdown, slack_text, config.output_dir)

    print(f"対象日: {report.target.date.isoformat()}  読み込み {load_result.rows_read}行 / "
          f"集計 {load_result.rows_kept}行 / 除外 {load_result.rows_dropped}行")
    for name, path in paths.items():
        print(f"  {name:<15} {path}")

    print("\n--- Slack通知文 ---")
    print(slack_text)
    if print_payload:
        print("\n--- Slackペイロード ---")
        print(json.dumps(build_slack_payload(slack_text, config.slack_channel), ensure_ascii=False, indent=2))

    status = f"設定済み {mask_secret(config.slack_webhook_url)}" if config.slack_configured else "未設定"
    print(f"\nSlack Webhook: {status}（このツールは送信せず、通知文の生成のみ行います）")
    return paths


def main(argv: list[str] | None = None) -> int:
    _make_console_safe()
    args = build_parser().parse_args(argv)
    try:
        config = load_config(dotenv_path=args.env_file)
        overrides = {
            key: value
            for key, value in {"input_path": args.input, "output_dir": args.output, "top_n": args.top}.items()
            if value is not None
        }
        if "top_n" in overrides and overrides["top_n"] <= 0:
            raise ValueError("--top は1以上で指定してください")
        config = replace(config, **overrides)
        run(config, target=args.date, print_payload=args.print_payload)
    except (FileNotFoundError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"エラー: ファイルの読み書きに失敗しました: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
