# GitHub Release Notifier - OCI Function

GitHubでウォッチしているOSSの新しいリリース情報を、LLMで要約してSlackへ自動通知するOCI Functionです。

## 機能

- 24時間以内のGitHub Notificationsを取得
- リリース通知のみをフィルタリング
- OpenAI（LangChain）でリリースノートを日本語要約
- Slackに通知（プレーンテキスト形式）
- テストモード対応（1件のみ送信）

## 必要な環境変数

OCI Functionsのアプリケーション設定で以下の環境変数を設定してください：

| 環境変数名 | 説明 | 必須 |
|-----------|------|------|
| `GITHUB_TOKEN` | GitHub Personal Access Token（`notifications`スコープ） | ✓ |
| `OPENAI_API_KEY` | OpenAI API Key | ✓ |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | ✓ |
| `OPENAI_MODEL` | OpenAIモデル名（デフォルト: `gpt-5-mini`） | |

## デプロイ方法

### 1. OCI CLIとfn CLIの設定

```bash
# OCI CLIの設定（初回のみ）
oci setup config

# fn CLIのコンテキスト設定
fn list contexts
fn use context <your-context>
```

### 2. アプリケーションの作成（初回のみ）

```bash
# OCIコンソールまたはCLIでアプリケーションを作成
fn create app github-release-app --annotation oracle.com/oci/subnetIds='["<subnet-ocid>"]'
```

### 3. 環境変数の設定

```bash
# アプリケーションに環境変数を設定
fn config app github-release-app GITHUB_TOKEN "your_github_token"
fn config app github-release-app OPENAI_API_KEY "your_openai_api_key"
fn config app github-release-app SLACK_WEBHOOK_URL "your_slack_webhook_url"
fn config app github-release-app OPENAI_MODEL "gpt-5-mini"
```

### 4. 関数のデプロイ

```bash
# このディレクトリで実行
fn deploy --app github-release-app
```

## ローカルテスト

デプロイせずにローカルで動作確認できます。

### 前提条件

```bash
# 依存パッケージをインストール（初回のみ）
cd github-release-notifier
pip install -r requirements.txt

# 環境変数を設定
export GITHUB_TOKEN='your_github_token'
export OPENAI_API_KEY='your_openai_api_key'
export SLACK_WEBHOOK_URL='your_slack_webhook_url'
export OPENAI_MODEL='gpt-5-mini'
```

### ローカルテストの実行方法

#### 1. Dry Run（Slackに送信せずに要約のみ表示）

```bash
python local_test.py --dry-run
```

#### 2. テストモード（1件のみSlackに送信）

```bash
python local_test.py --test-mode
```

#### 3. 通常実行（24時間分のリリース通知を処理）

```bash
python local_test.py
```

#### 4. 取得期間を指定

```bash
python local_test.py --since-hours 48
```

#### 5. オプション組み合わせ

```bash
# 48時間分をDry Runで確認
python local_test.py --since-hours 48 --dry-run

# 1件のみテスト送信
python local_test.py --test-mode
```

### ローカルテストのメリット

- デプロイ不要で高速にテスト可能
- `--dry-run` でSlack送信せずに要約結果を確認
- デバッグが容易（通常のPythonスクリプトとして実行）
- プロンプトテンプレートの調整がしやすい

## OCI Functionとしての実行方法

### 通常実行（24時間分のリリース通知を処理）

```bash
fn invoke github-release-app github-release-notifier
```

### テストモード（1件のみ送信）

```bash
echo '{"test_mode": true}' | fn invoke github-release-app github-release-notifier
```

### 取得期間を指定

```bash
echo '{"since_hours": 48}' | fn invoke github-release-app github-release-notifier
```

## レスポンス例

### 成功時

```json
{
  "message": "GitHub Release notifications processed",
  "test_mode": false,
  "since_hours": 24,
  "notifications_total": 15,
  "release_notifications": 3,
  "sent": 3,
  "errors": null
}
```

### エラー時

```json
{
  "error": "GITHUB_TOKEN environment variable is not set"
}
```

## スケジュール実行

OCIのリソース・スケジューラを使用して定期実行できます：

1. OCIコンソールで「リソース・スケジューラ」を開く
2. 新しいスケジュールを作成
3. アクション: Function実行
4. 関数: `github-release-notifier`
5. ペイロード: `{}`（通常実行）または `{"test_mode": true}`（テストモード）
6. スケジュール: Cron式で設定（例: `0 9 * * *` = 毎日9時）

## ログの確認

```bash
# 最新のログを確認
fn invoke github-release-app github-release-notifier --verbose

# OCIコンソールでログを確認
# [監視および管理] → [ログ] → [ログの探索]
```

## トラブルシューティング

### メモリ不足エラー

`func.yaml`の`memory`を増やしてください（現在: 1024MB）

### タイムアウトエラー

`func.yaml`の`timeout`を増やしてください（現在: 300秒）

### LLM要約エラー

- `OPENAI_API_KEY`が正しく設定されているか確認
- OpenAI APIの使用制限を確認
- モデル名が正しいか確認（`OPENAI_MODEL`）

## プロンプトテンプレートのカスタマイズ

LLMの要約動作は `prompt_template.txt` ファイルで制御されています。

### プロンプトテンプレートの編集

要約の観点やフォーマットを変更したい場合は、`prompt_template.txt` を編集してください：

```bash
# テンプレートを編集
vi prompt_template.txt

# 再デプロイ
fn deploy --app github-release-app
```

### テンプレートの内容

- 要約の観点（新機能重視、バグ修正無視など）
- 出力フォーマット（箇条書き、文字数制限など）
- 出力例

デフォルトでは2000文字以内の箇条書き形式で日本語要約を生成します。

## ファイル構成

```
github-release-notifier/
├── func.yaml              # Function設定
├── func.py                # メインハンドラー（OCI Function用）
├── local_test.py          # ローカルテストスクリプト
├── github_client.py       # GitHub API操作
├── llm_summarizer.py      # LLM要約
├── slack_notifier.py      # Slack通知
├── prompt_template.txt    # LLMプロンプトテンプレート
├── requirements.txt       # 依存パッケージ
└── README.md              # このファイル
```
