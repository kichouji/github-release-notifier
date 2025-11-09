# GitHub Release 通知自動投稿ツール

GitHubでウォッチしているOSSの新しいリリース情報を、要約付きでSlackへ自動通知するツールです。

## プロジェクト構成

```
github-release-notifier/
├── github-release-notifier/        # OCI Function（本番アプリケーション）
│   ├── func.yaml                   # Function設定
│   ├── func.py                     # メインハンドラー
│   ├── local_test.py               # ローカルテストスクリプト
│   ├── github_client.py            # GitHub API操作
│   ├── llm_summarizer.py           # LLM要約
│   ├── slack_notifier.py           # Slack通知
│   ├── prompt_template.txt         # LLMプロンプトテンプレート
│   ├── requirements.txt            # 依存パッケージ
│   └── README.md                   # デプロイ手順
├── .env.example                   # 環境変数のサンプル
└── README.md                      # このファイル
```

## セットアップ

### 1. Python仮想環境の作成

```bash
# 仮想環境を作成
python3 -m venv venv

# 仮想環境を有効化
source venv/bin/activate  # Linux/macOS
# または
venv\Scripts\activate  # Windows
```

### 2. 依存パッケージのインストール

```bash
pip install -r github-release-notifier/requirements.txt
```

### 3. API キーの取得

#### GitHub Personal Access Token

1. GitHubにログインして [Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) にアクセス
2. "Generate new token (classic)" をクリック
3. 必要なスコープを選択:
   - `notifications` (必須)
4. トークンを生成してコピー

#### OpenAI API Key

1. [OpenAI Platform](https://platform.openai.com/api-keys) にアクセス
2. "Create new secret key" をクリック
3. APIキーを生成してコピー

#### Slack Webhook URL

1. [Slack API: Incoming Webhooks](https://api.slack.com/messaging/webhooks) にアクセス
2. "Create your Slack app" から新しいアプリを作成、または既存のアプリを選択
3. "Incoming Webhooks" を有効化
4. "Add New Webhook to Workspace" をクリック
5. 通知を送信するチャンネルを選択
6. 生成されたWebhook URLをコピー

### 4. 環境変数の設定

```bash
export GITHUB_TOKEN='your_github_personal_access_token_here'
export OPENAI_API_KEY='your_openai_api_key_here'
export OPENAI_MODEL='gpt-5-mini'  # 使用するモデル
export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
```

または、`.env`ファイルを作成:

```bash
cp .env.example .env
# .env ファイルを編集してトークンとAPIキーを設定
```

## 機能

- GitHub Notificationsから24時間以内のリリース情報を取得
- OpenAI（LangChain）でリリースノートを日本語要約
- Slackへ自動通知
- OCI Functions対応
- ローカルテスト実行可能（Dry Run / Test Mode）

## OCI Functionのデプロイ

本番アプリケーションは `github-release-notifier/` ディレクトリにあります。

### ローカルテスト（デプロイ不要）

デプロイする前にローカルで動作確認できます：

```bash
cd github-release-notifier

# 依存パッケージをインストール
pip install -r requirements.txt

# 環境変数を設定
export GITHUB_TOKEN='your_github_token'
export OPENAI_API_KEY='your_openai_api_key'
export SLACK_WEBHOOK_URL='your_slack_webhook_url'

# Dry Run（Slackに送信せずに要約のみ表示）
python local_test.py --dry-run

# テストモード（1件のみSlackに送信）
python local_test.py --test-mode
```

### クイックスタート（OCI Functionへのデプロイ）

```bash
cd github-release-notifier

# アプリケーションを作成（初回のみ）
fn create app github-release-app --annotation oracle.com/oci/subnetIds='["<subnet-ocid>"]'

# 環境変数を設定
fn config app github-release-app GITHUB_TOKEN "your_github_token"
fn config app github-release-app OPENAI_API_KEY "your_openai_api_key"
fn config app github-release-app SLACK_WEBHOOK_URL "your_slack_webhook_url"

# デプロイ
fn deploy --app github-release-app

# テスト実行（1件のみ送信）
echo '{"test_mode": true}' | fn invoke github-release-app github-release-notifier

# 通常実行（24時間分のリリース通知を処理）
fn invoke github-release-app github-release-notifier
```

詳細は [github-release-notifier/README.md](./github-release-notifier/README.md) を参照してください。

## ライセンス

MIT
