from __future__ import annotations

import io
import json

import pytest

from sales_pipeline import cli
from sales_pipeline.cli import main

ENV_KEYS = (
    "SALES_INPUT_PATH",
    "SALES_OUTPUT_DIR",
    "SALES_TOP_N",
    "SALES_CURRENCY_LABEL",
    "SLACK_WEBHOOK_URL",
    "SLACK_CHANNEL",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """実行環境の環境変数がテスト結果に影響しないようにする。"""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def no_env_file(tmp_path):
    return ["--env-file", str(tmp_path / "none.env")]


def test_end_to_end(tmp_path, sample_csv, capsys, no_env_file):
    exit_code = main(["-i", str(sample_csv), "-o", str(tmp_path), *no_env_file])

    assert exit_code == 0
    day_dir = tmp_path / "2026-11-18"
    for name in ("report.md", "daily_summary.csv", "products.csv", "categories.csv", "slack_message.txt"):
        assert (day_dir / name).exists()

    report = (day_dir / "report.md").read_text(encoding="utf-8")
    assert "| 売上 | 32,540円 | +52.1% |" in report

    out = capsys.readouterr().out
    assert "読み込み 34行 / 集計 30行 / 除外 4行" in out
    assert "Slack Webhook: 未設定" in out


def test_specific_date_and_payload(tmp_path, sample_csv, capsys, monkeypatch, no_env_file):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T0/B0/secret1234")
    monkeypatch.setenv("SLACK_CHANNEL", "#sales")

    exit_code = main(["-i", str(sample_csv), "-o", str(tmp_path), "-d", "2026-11-17", "--top", "2",
                      "--print-payload", *no_env_file])

    assert exit_code == 0
    assert (tmp_path / "2026-11-17" / "report.md").exists()
    out = capsys.readouterr().out
    payload = json.loads(out.split("--- Slackペイロード ---")[1].split("\nSlack Webhook:")[0])
    assert payload["channel"] == "#sales"
    assert "2026-11-17" in payload["text"]
    # Webhook URL は伏せて表示され、生成物にも含まれない
    assert "secret1234" not in out
    assert "********1234" in out
    assert "hooks.slack.com" not in (tmp_path / "2026-11-17" / "slack_message.txt").read_text(encoding="utf-8")


def test_payload_without_slack_settings(tmp_path, sample_csv, capsys, no_env_file):
    assert main(["-i", str(sample_csv), "-o", str(tmp_path), "--print-payload", *no_env_file]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out.split("--- Slackペイロード ---")[1].split("\nSlack Webhook:")[0])
    assert set(payload) == {"text"}
    assert "Slack Webhook: 未設定" in out


def test_dotenv_file_is_used(tmp_path, sample_csv):
    env_file = tmp_path / ".env"
    env_file.write_text(f"SALES_INPUT_PATH={sample_csv}\nSALES_OUTPUT_DIR={tmp_path / 'out'}\n", encoding="utf-8")
    assert main(["--env-file", str(env_file)]) == 0
    assert (tmp_path / "out" / "2026-11-18" / "report.md").exists()


def test_missing_input_returns_error(tmp_path, capsys, no_env_file):
    assert main(["-i", str(tmp_path / "missing.csv"), "-o", str(tmp_path), *no_env_file]) == 1
    assert "入力CSVが見つかりません" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "CSVが空です"),
        ("注文ID,注文日,商品名,数量,単価\n".encode(), "集計対象のデータが0件です"),
        ("商品名,数量\n豆,1\n".encode(), "必須列が見つかりません"),
        ("注文ID,注文日,商品名,数量,単価\n1,不明,豆,1,100\n".encode(), "集計対象のデータが0件です"),
    ],
    ids=["empty", "header_only", "missing_columns", "all_rows_invalid"],
)
def test_bad_csv_returns_error(tmp_path, capsys, no_env_file, content, message):
    path = tmp_path / "bad.csv"
    path.write_bytes(content)
    assert main(["-i", str(path), "-o", str(tmp_path / "out"), *no_env_file]) == 1
    assert message in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_directory_input_returns_error(tmp_path, capsys, no_env_file):
    assert main(["-i", str(tmp_path), "-o", str(tmp_path / "out"), *no_env_file]) == 1
    assert "ファイルではありません" in capsys.readouterr().err


def test_date_out_of_range_returns_error(tmp_path, sample_csv, capsys, no_env_file):
    assert main(["-i", str(sample_csv), "-o", str(tmp_path), "-d", "2027-01-01", *no_env_file]) == 1
    assert "2026-11-16 〜 2026-11-18" in capsys.readouterr().err


@pytest.mark.parametrize("top", ["0", "-1"])
def test_invalid_top_returns_error(tmp_path, sample_csv, capsys, no_env_file, top):
    assert main(["-i", str(sample_csv), "-o", str(tmp_path), "--top", top, *no_env_file]) == 1
    assert "--top は1以上" in capsys.readouterr().err


def test_invalid_top_n_env_returns_error(tmp_path, sample_csv, capsys, monkeypatch, no_env_file):
    monkeypatch.setenv("SALES_TOP_N", "many")
    assert main(["-i", str(sample_csv), "-o", str(tmp_path), *no_env_file]) == 1
    assert "SALES_TOP_N" in capsys.readouterr().err


def test_write_permission_error_returns_error(tmp_path, sample_csv, capsys, monkeypatch, no_env_file):
    def deny(*_args, **_kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(cli, "write_outputs", deny)
    assert main(["-i", str(sample_csv), "-o", str(tmp_path), *no_env_file]) == 1
    assert "ファイルの読み書きに失敗しました" in capsys.readouterr().err


def test_console_without_unicode_support_does_not_crash(tmp_path, sample_csv, monkeypatch, no_env_file):
    """Windows のリダイレクト先（cp932）のように「•」を表示できない出力先でも落ちない。"""
    buffer = io.BytesIO()
    monkeypatch.setattr("sys.stdout", io.TextIOWrapper(buffer, encoding="cp932"))
    assert main(["-i", str(sample_csv), "-o", str(tmp_path), *no_env_file]) == 0
    assert (tmp_path / "2026-11-18" / "slack_message.txt").read_text(encoding="utf-8").count("•") == 3


def test_invalid_date_format_exits_with_code_2(no_env_file):
    with pytest.raises(SystemExit) as excinfo:
        main(["-d", "2026/11/18", *no_env_file])
    assert excinfo.value.code == 2
