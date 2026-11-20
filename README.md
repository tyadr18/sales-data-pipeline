# sales-data-pipeline

[![tests](https://github.com/tyadr18/sales-data-pipeline/actions/workflows/test.yml/badge.svg)](https://github.com/tyadr18/sales-data-pipeline/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> A small Python 3.12 + pandas tool that cleans messy e-commerce sales CSVs, aggregates them by day, product and category, and outputs a daily report (Markdown/CSV) plus a ready-to-post Slack message. Tested with pytest on Linux and Windows via GitHub Actions.

EC サイトの売上CSVを取り込み、表記ゆれを整えてから集計し、日次レポート（Markdown / CSV）と Slack 通知用の文面までを1コマンドで作る自動化ツールです。

※ポートフォリオ用の作例です。実在するクライアントの案件ではありません。サンプルデータの商品名・数値はすべて架空のもので、個人情報は含んでいません。

---

## 概要

EC の管理画面から書き出した CSV は、列名が日本語だったり英語だったり、金額に「¥」や「,」が付いていたり、日付の書き方がバラバラだったりします。毎日の売上報告を手作業でまとめると、この整形に時間を取られがちです。

このツールは次の流れを自動で行います。

1. **読み込み・整形**：列名のゆれを吸収し、金額・数量・日付を正しい型にそろえます。使えない行は理由ごとに件数を記録して除外します。
2. **集計**：日次・商品別・カテゴリ別に、売上・注文件数・販売数量・平均単価を計算します。
3. **出力**：対象日の日次レポートを Markdown と CSV で書き出します。前日比も付けます。
4. **通知文の生成**：Slack にそのまま貼れるテキストと、Incoming Webhook 用の JSON ペイロードを作ります。

Slack への送信そのものは行いません。Webhook URL は環境変数で受け取る前提で、画面に表示するときは末尾4文字以外を伏せます。

### 出力例（サンプルデータ・2026-11-18 分）

Slack 通知文：

```text
*:bar_chart: 日次売上レポート 2026-11-18*
• 売上: 32,540円（前日比 +52.1%）
• 注文件数: 9件（前日比 +50.0%）
• 平均単価: 3,616円（前日比 +1.4%）

*売上上位3商品*
1. ハウスブレンド豆 200g  7,680円（6点）
2. ドリップバッグ 10袋  5,880円（6点）
3. ステンレスタンブラー 350ml  4,960円（2点）

最も売れたカテゴリ: コーヒー（構成比 54.4%）
```

Markdown レポート（冒頭とデータ品質欄の抜粋）：

```markdown
## サマリー

| 指標 | 値 | 前日比 |
| :--- | ---: | ---: |
| 売上 | 32,540円 | +52.1% |
| 注文件数 | 9件 | +50.0% |
| 販売数量 | 25点 | +56.2% |
| 平均単価 | 3,616円 | +1.4% |

## データ品質

- 読み込み行数: 34
- 集計対象行数: 30
- 除外行数: 4
  - 日付が不正: 1
  - 商品名なし: 1
  - 数量が不正: 1
  - 重複行: 1
- カテゴリ空欄の補完: 2（同一商品のカテゴリから 2 / 未分類 0）
```

レポートにはこのほか、商品別ランキング、カテゴリ別の構成比、日次推移も入ります。

## 使った技術

| 項目 | 内容 |
| :--- | :--- |
| 言語 | Python 3.12（3.13 でも動作確認） |
| データ処理 | pandas（2.2〜3.x） |
| テスト | pytest（101件。単体テスト、境界値・異常系、CLI の通しテスト） |
| CI | GitHub Actions（Ubuntu / Windows × Python 3.12 / 3.13） |
| パッケージ構成 | `pyproject.toml`（setuptools、src レイアウト） |
| 設定 | 環境変数 / `.env`（外部ライブラリなしの簡易パーサ） |
| CLI | argparse（`sales-pipeline` コマンド / `python -m sales_pipeline`） |

依存ライブラリは pandas だけです（テスト時は pytest も使います）。

## 動かし方

### 1. セットアップ

```bash
git clone https://github.com/tyadr18/sales-data-pipeline.git
cd sales-data-pipeline

python3.12 -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1

pip install -e ".[dev]"          # または pip install -r requirements.txt
```

### 2. 設定（任意）

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

| 環境変数 | 既定値 | 説明 |
| :--- | :--- | :--- |
| `SALES_INPUT_PATH` | `data/sample_sales.csv` | 入力CSVのパス |
| `SALES_OUTPUT_DIR` | `reports` | 出力先ディレクトリ |
| `SALES_TOP_N` | `5` | 商品ランキングの件数（1以上） |
| `SALES_CURRENCY_LABEL` | `円` | 金額の単位表記 |
| `SLACK_WEBHOOK_URL` | （なし） | Slack Webhook URL。送信はせず、設定の有無だけ表示します |
| `SLACK_CHANNEL` | （なし） | ペイロードに含める通知先チャンネル |

値は「CLI 引数 → 環境変数 → `.env` → 既定値」の順で優先されます。`.env` は `.gitignore` に入れてあるので、Webhook URL をうっかりコミットすることはありません。

### 3. 実行

```bash
# サンプルデータの最新日（2026-11-18）でレポートを作る
sales-pipeline

# 入力・出力・対象日・ランキング件数を指定する
sales-pipeline -i data/sample_sales.csv -o reports -d 2026-11-17 --top 3

# Slack 送信用の JSON ペイロードも表示する
sales-pipeline --print-payload
```

`pip install -e .` をしていない場合は `PYTHONPATH=src python -m sales_pipeline` で同じように動きます。

出力先には日付ごとのフォルダができます。同じ日付で再実行すると上書きします。

```text
reports/2026-11-18/
├── report.md            # 日次レポート（Markdown）
├── daily_summary.csv    # 日次推移（全期間）
├── products.csv         # 商品別集計（対象日）
├── categories.csv       # カテゴリ別集計（対象日・構成比付き）
└── slack_message.txt    # Slack 通知文
```

終了コードは、成功で `0`、入力・設定・出力のエラーで `1`（理由を標準エラーに表示）、引数の誤りで `2` です。cron やタスクスケジューラから呼んでも、失敗を判定できます。

### 4. テスト

```bash
pytest
```

警告もエラーとして扱う設定（`filterwarnings = error`）にしてあるので、pandas の将来の非互換もテストで早めに気づけます。`main` ブランチへの push と Pull Request のたびに、GitHub Actions が Ubuntu と Windows でテストを流し、サンプルデータで CLI も実行します。

## 工夫点

**列名のゆれを辞書で吸収する**
`Order ID`・`注文ID`・`受注番号`、`unit price`・`単価` など、よくある呼び方を正規の列名に寄せる対応表を持たせました。比較の前に全角→半角、大文字→小文字、空白・ハイフン→アンダースコアの変換をかけるので、`ＱＴＹ` や ` Order ID ` のような書き方でも認識できます。対応する列が増えたら、対応表に1行足すだけで済みます。

**値の表記ゆれを整える**
金額は `¥1,280`・`１,３８０円`・`"2,480"`、日付は `2026/11/16`・`2026年11月17日`・`2026-11-18 14:05`・`2026-11-18T10:00:00+09:00` のような書き方をどれも受け付けます。商品名に紛れ込んだ改行や連続した空白は、半角スペース1つにまとめます。単価と金額はどちらか片方があれば、もう片方を計算で補います。UTF-8（BOM 付きを含む）で読めないときは Shift_JIS（cp932）で読み直します。

**黙って捨てない**
日付が読めない、商品名がない、数量が0以下・小数・空欄、金額がマイナスか空欄、重複行。こうした行は除外しますが、理由ごとの件数をレポートの「データ品質」欄に出します。集計結果の数字がどこまで信用できるかを、読む人が自分で判断できるようにするためです。

**カテゴリの空欄は同じ商品から補う**
カテゴリが空欄の行は、同じ商品のほかの行で一番多いカテゴリで埋めます。それでも分からないときだけ「未分類」にします。単純に「未分類」で埋めると、同じ商品が2行に分かれてランキングがずれてしまうので、それを防いでいます。

**比較の基準を正直に書く**
比較相手はデータ内で対象日の直前にある日です。暦の前日であれば「前日比」、土日が抜けているなど間が空いていれば「前回比」と表示を変えます。前日比のつもりで3日前と比べていた、という誤読を防ぐためです。

**指標の定義をはっきりさせる**
「平均単価」は「売上 ÷ 注文件数」（客単価）と定義し、コードの docstring とレポートの注記に書きました。1つの注文に複数カテゴリの商品があるときは、カテゴリ別の内訳でそれぞれ1件として数えます。この扱いもテストで固定しています。

**秘密情報を出さない**
Webhook URL はコードにもリポジトリにも置かず、環境変数で受け取ります。コンソールには `********1234` のように伏せて表示し、URL が画面にも生成ファイルにも含まれないことをテストで確認しています。

**どの環境でも途中で落ちない**
Windows で出力をリダイレクトすると標準出力が cp932 などになり、「•」が表示できずに途中で止まることがあります。表示できない文字は置き換えて最後まで処理するようにしました。空のCSV、ヘッダーだけのCSV、ディレクトリの指定、書き込み権限のない出力先も、トレースバックではなく日本語のエラーメッセージで終わります。Slack の制御文字（`&` `<` `>`）や Markdown の表を壊す文字（`|` と改行）もエスケープします。

**処理を分けてテストしやすくする**
読み込み（`loader`）、集計（`aggregate`）、出力（`report`）、通知文（`notify`）、設定（`config`）、CLI（`cli`）をモジュールごとに分け、どれも DataFrame や dataclass を受け取って返す形にしました。ファイルを用意しなくても単体でテストできます。CLI は終了コードを返す `main()` にしてあり、通しのテストも書けます。

## 前提と制約

- **重複行の定義**：注文ID・日付・商品名・数量・単価がすべて同じ行を、二重出力とみなして除外します。同じ注文の同じ商品を同数・同単価で2行に分けて記録するデータでは、件数が減ります。
- **タイムゾーン**：タイムゾーン付きの日時は、オフセットを外して表記どおりの日付で集計します（日本時間に換算し直すことはしません）。
- **返品・キャンセル**：マイナスの数量・金額は不正な行として除外します。返品の相殺には対応していません。
- **同じ商品名で別カテゴリ**：データ内で同じ商品名に異なるカテゴリが付いていると、商品別ランキングでは別の行として出ます。
- **`.env` の書式**：`KEY=VALUE` の形だけに対応しています。値の後ろに `# コメント` は書けません（`#sales` のようなチャンネル名と区別できないため）。
- **Slack 送信**：通知文とペイロードの生成までです。送信する場合は、生成された `slack_message.txt` かペイロードを別の仕組みで POST してください。

## ディレクトリ構成

```text
sales-data-pipeline/
├── README.md
├── LICENSE
├── pyproject.toml            # パッケージ定義・pytest 設定・CLI エントリポイント
├── requirements.txt
├── .env.example              # 設定サンプル（.env にコピーして使う）
├── .gitignore
├── .github/
│   └── workflows/
│       └── test.yml          # GitHub Actions（pytest と CLI の動作確認）
├── data/
│   └── sample_sales.csv      # 架空の売上データ（表記ゆれ・欠損をわざと含む）
├── src/
│   └── sales_pipeline/
│       ├── __init__.py
│       ├── __main__.py       # python -m sales_pipeline
│       ├── cli.py            # コマンドライン実行・終了コード
│       ├── config.py         # 環境変数・.env の読み込み
│       ├── loader.py         # CSV 読み込み・列名の正規化・型の整形
│       ├── aggregate.py      # 日次・商品別・カテゴリ別集計
│       ├── report.py         # Markdown / CSV 出力
│       └── notify.py         # Slack 通知文・ペイロード生成
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_loader.py
    ├── test_aggregate.py
    ├── test_report.py
    ├── test_notify.py
    └── test_cli.py
```

## ライセンス

[MIT License](LICENSE)
