# GEMINI.md

## 目的
- Gemini CLI 向けのコンテキストと作業方針を定義する。

## 出力スタイル
- 言語: 日本語
- トーン: 簡潔で事実ベース
- 形式: Markdown

## 共通ルール
- 会話は日本語で行う。
- PR とコミットは Conventional Commits に従う。
- PR タイトルとコミット本文の言語: PR タイトルは Conventional Commits 形式（英語推奨）。PR 本文は日本語。コミットは Conventional Commits 形式（description は日本語）。
- 日本語と英数字の間には半角スペースを入れる。

## プロジェクト概要
Automatically updates Docker Compose image tags from 'latest' to actual versions with optional Discord webhook notifications.

### 技術スタック
- **言語**: Python, Bash
- **パッケージマネージャー**: pip
- **主要な依存関係**:
  - python:
    - requests==2.28.1

## コーディング規約
- フォーマット: 既存設定（ESLint / Prettier / formatter）に従う。
- 命名規則: 既存のコード規約に従う。
- コメント言語: 日本語
- エラーメッセージ: 英語

### 開発コマンド
```bash
# install
pip install -r requirements.txt

# usage
python -m src <project_dir>

# cron
update-all.sh /path/to/projects /path/to/logs

# systemd
ExecStartPre=/path/to/wrapper.sh

```

## 注意事項
- 認証情報やトークンはコミットしない。
- ログに機密情報を出力しない。
- 既存のプロジェクトルールがある場合はそれを優先する。

## リポジトリ固有
- **type**: Automation Tool
- **entry_point**: python -m src
**functions:**
  - Read docker-compose.yml files
  - Extract image tags
  - Pull latest images
  - Update compose files
  - Send Discord notifications
**supported_compose_files:**
  - docker-compose.yml
  - compose.yaml
  - compose.yml
- **optional_discord_webhook**: discord_webhook_url.txt