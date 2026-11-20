"""設定値の読み込み。

優先順位は「CLI引数 > 環境変数 > .env ファイル > デフォルト値」。
.env の読み込みは外部ライブラリに頼らず、最小限のパーサで行う。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INPUT_PATH = "data/sample_sales.csv"
DEFAULT_OUTPUT_DIR = "reports"
DEFAULT_TOP_N = 5
DEFAULT_CURRENCY_LABEL = "円"


@dataclass(frozen=True)
class Config:
    input_path: Path
    output_dir: Path
    top_n: int = DEFAULT_TOP_N
    currency_label: str = DEFAULT_CURRENCY_LABEL
    slack_webhook_url: str | None = None
    slack_channel: str | None = None

    @property
    def slack_configured(self) -> bool:
        """Webhook URL が設定されているか（このツール自体は送信しない）。"""
        return bool(self.slack_webhook_url)


def parse_dotenv(path: Path) -> dict[str, str]:
    """`KEY=VALUE` 形式の .env ファイルを辞書にする。

    空行と `#` で始まる行は無視し、値を囲む引用符は取り除く。
    """
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _parse_positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} は整数で指定してください: {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} は1以上で指定してください: {value}")
    return value


def load_config(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = Path(".env"),
) -> Config:
    """環境変数（と .env）から Config を作る。

    テストでは `env` に辞書を渡し、`dotenv_path=None` にすると
    実行環境に左右されずに検証できる。
    """
    values: dict[str, str] = {}
    if dotenv_path is not None and dotenv_path.exists():
        values.update(parse_dotenv(dotenv_path))
    values.update(os.environ if env is None else env)

    def get(key: str) -> str | None:
        value = values.get(key, "").strip()
        return value or None

    top_n_raw = get("SALES_TOP_N")
    return Config(
        input_path=Path(get("SALES_INPUT_PATH") or DEFAULT_INPUT_PATH),
        output_dir=Path(get("SALES_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR),
        top_n=_parse_positive_int(top_n_raw, "SALES_TOP_N") if top_n_raw else DEFAULT_TOP_N,
        currency_label=get("SALES_CURRENCY_LABEL") or DEFAULT_CURRENCY_LABEL,
        slack_webhook_url=get("SLACK_WEBHOOK_URL"),
        slack_channel=get("SLACK_CHANNEL"),
    )
