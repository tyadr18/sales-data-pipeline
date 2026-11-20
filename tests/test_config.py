from __future__ import annotations

from pathlib import Path

import pytest

from sales_pipeline.config import DEFAULT_TOP_N, load_config, parse_dotenv


def test_defaults_when_env_is_empty():
    config = load_config(env={}, dotenv_path=None)
    assert config.input_path == Path("data/sample_sales.csv")
    assert config.output_dir == Path("reports")
    assert config.top_n == DEFAULT_TOP_N
    assert config.currency_label == "円"
    assert config.slack_configured is False


def test_values_from_env():
    config = load_config(
        env={
            "SALES_INPUT_PATH": "in.csv",
            "SALES_OUTPUT_DIR": "out",
            "SALES_TOP_N": "10",
            "SALES_CURRENCY_LABEL": " JPY",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/x",
            "SLACK_CHANNEL": "#sales",
        },
        dotenv_path=None,
    )
    assert config.input_path == Path("in.csv")
    assert config.output_dir == Path("out")
    assert config.top_n == 10
    assert config.slack_configured is True
    assert config.slack_channel == "#sales"


def test_blank_values_fall_back_to_defaults():
    config = load_config(env={"SALES_TOP_N": "", "SLACK_WEBHOOK_URL": "  "}, dotenv_path=None)
    assert config.top_n == DEFAULT_TOP_N
    assert config.slack_webhook_url is None


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_invalid_top_n(value):
    with pytest.raises(ValueError, match="SALES_TOP_N"):
        load_config(env={"SALES_TOP_N": value}, dotenv_path=None)


def test_parse_dotenv(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n\nSALES_TOP_N=3\nexport SLACK_CHANNEL='#report'\nSALES_OUTPUT_DIR=\"out dir\"\nbroken line\n",
        encoding="utf-8",
    )
    assert parse_dotenv(path) == {"SALES_TOP_N": "3", "SLACK_CHANNEL": "#report", "SALES_OUTPUT_DIR": "out dir"}


def test_env_overrides_dotenv(tmp_path):
    path = tmp_path / ".env"
    path.write_text("SALES_TOP_N=3\nSALES_OUTPUT_DIR=from_dotenv\n", encoding="utf-8")
    config = load_config(env={"SALES_TOP_N": "7"}, dotenv_path=path)
    assert config.top_n == 7
    assert config.output_dir == Path("from_dotenv")
