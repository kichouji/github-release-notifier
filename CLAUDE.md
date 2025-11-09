# GitHub Release Notifier - プロジェクト定義

## プロジェクト概要

GitHubでウォッチしているOSSの新しいリリース情報を、LLMで要約してSlackへ自動通知するOCI Functions実装。

## 技術スタック

- **言語**: Python 3.11
- **実行環境**: OCI Functions (Oracle Cloud Infrastructure)
- **主要ライブラリ**:
  - `requests`: GitHub API、Slack API通信
  - `langchain-openai`: LLM要約処理
  - `fdk`: OCI Functions Python SDK

## プロジェクト構造

```
github-release-notifier/
├── github-release-notifier/        # OCI Function（本番アプリケーション）
│   ├── func.yaml                   # Function設定（メモリ、タイムアウト、ランタイム）
│   ├── func.py                     # メインハンドラー（OCI Function エントリーポイント）
│   ├── local_test.py               # ローカルテストスクリプト
│   ├── github_client.py            # GitHub Notifications API操作
│   ├── llm_summarizer.py           # LLM要約処理（LangChain + OpenAI）
│   ├── slack_notifier.py           # Slack通知処理（Webhook）
│   ├── prompt_template.txt         # LLMプロンプトテンプレート
│   └── requirements.txt            # 依存パッケージ
├── .env.example                    # 環境変数のサンプル
└── README.md                       # プロジェクトドキュメント
```

## コアモジュール

### 1. `func.py` - メインハンドラー
- OCI Functionのエントリーポイント
- リクエストパラメータ処理（test_mode, since_hours）
- 各モジュールの呼び出しとエラーハンドリング
- レスポンス生成

### 2. `github_client.py` - GitHub API操作
- `get_notifications()`: GitHub Notifications API呼び出し
- 24時間以内のリリース通知をフィルタリング
- Personal Access Token認証

### 3. `llm_summarizer.py` - LLM要約
- `summarize_release_notes()`: リリースノートを日本語要約
- LangChain + OpenAI APIを使用
- プロンプトテンプレートから要約指示を読み込み
- 要約観点: 新機能重視、バグ修正無視、2000文字以内

### 4. `slack_notifier.py` - Slack通知
- `send_to_slack()`: Incoming Webhook経由でメッセージ送信
- プレーンテキスト形式
- エラー時の詳細ログ出力

## 環境変数

### 必須
- `GITHUB_TOKEN`: GitHub Personal Access Token（`notifications`スコープ）
- `OPENAI_API_KEY`: OpenAI API Key
- `SLACK_WEBHOOK_URL`: Slack Incoming Webhook URL

### オプション
- `OPENAI_MODEL`: OpenAIモデル名（デフォルト: `gpt-5-mini`）

## デプロイメント

### ローカルテスト
```bash
cd github-release-notifier
pip install -r requirements.txt
export GITHUB_TOKEN='...'
export OPENAI_API_KEY='...'
export SLACK_WEBHOOK_URL='...'
python local_test.py --dry-run  # Slack送信なし
python local_test.py --test-mode  # 1件のみ送信
```

### OCI Functionsデプロイ
```bash
fn create app github-release-app --annotation oracle.com/oci/subnetIds='["<subnet-ocid>"]'
fn config app github-release-app GITHUB_TOKEN "..."
fn config app github-release-app OPENAI_API_KEY "..."
fn config app github-release-app SLACK_WEBHOOK_URL "..."
fn deploy --app github-release-app
```

### 実行方法
```bash
# 通常実行（24時間分）
fn invoke github-release-app github-release-notifier

# テストモード（1件のみ）
echo '{"test_mode": true}' | fn invoke github-release-app github-release-notifier
```

## 重要な制約事項

### OCI Functions特有の制約
1. **非同期処理の制限**: `asyncio.run()`はOCI Functions環境で動作しないため、`ThreadPoolExecutor`を使用
2. **メモリ制限**: func.yamlで1024MB設定
3. **タイムアウト**: func.yamlで300秒（5分）設定

### API制限
- **GitHub API**: 認証済みで5000リクエスト/時
- **OpenAI API**: モデルとプランによる制限あり
- **Slack Webhook**: プレーンテキスト最大40,000文字

## LLM要約の観点

`prompt_template.txt`で定義:
- 新機能（FEATURE）を最も重視
- 機能の変更、インターフェース/APIの変更（ENHANCEMENT）を重視
- 内部コンポーネントのバージョンアップは優先度低
- 小さなバグ修正やドキュメント修正は無視
- 箇条書き形式で出力
- 2000文字以内の日本語で出力

## セキュリティ要件

### 非公開情報
- `.env`: 環境変数（実際のトークン、APIキー）
- `tests/`: テストコードとサンプルデータ
- `構築手順書.md`, `oci_github_release_notice_requirements.md`, `TROUBLESHOOTING_REPORT.md`: 個人的なドキュメント
- `.claude/`: Claude Code設定
- `venv/`: Python仮想環境

### GitHub公開ファイル
- アプリケーションコード（`github-release-notifier/`）
- README.md、.env.example
- .gitignore

## 開発ガイドライン

### コード編集時の注意点
1. **エラーハンドリング**: 各API呼び出しは適切にtry-exceptで処理
2. **ログ出力**: デバッグ用にprintでログ出力（OCI Functionsログに表示される）
3. **環境変数チェック**: 起動時に必須環境変数の存在を確認
4. **テストモード**: `test_mode`パラメータで1件のみ処理する機能を維持

### プロンプト編集
- `prompt_template.txt`を編集後、再デプロイが必要
- ローカルテストで動作確認してからデプロイ

### バージョン管理
- `func.yaml`のversionフィールドでバージョン管理
- 現在: v0.0.16

## トラブルシューティング

### よくある問題
1. **メモリ不足**: func.yamlのmemoryを増やす
2. **タイムアウト**: func.yamlのtimeoutを増やす
3. **LLM要約エラー**: OPENAI_API_KEYとモデル名を確認
4. **Slack送信失敗**: Webhook URLの有効性を確認

### デバッグ方法
1. ローカルテストで`--dry-run`を使用
2. OCI Functionsログを確認: `fn invoke --verbose`
3. OCIコンソールのログ探索を使用
