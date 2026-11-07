#!/usr/bin/env python3
"""
ローカルテストスクリプト
OCI Functionのロジックを fn invoke を使わずにローカルで実行します
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# 同じディレクトリのモジュールをインポート
sys.path.insert(0, str(Path(__file__).parent))

from github_client import GitHubClient
from llm_summarizer import LLMSummarizer
from slack_notifier import SlackNotifier
from func import _extract_release_info, order_releases, summarize_releases_parallel


def _create_console_logger() -> logging.Logger:
    """コンソールにメッセージのみを出力するロガーを作成"""
    logger = logging.getLogger("local_test")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description='GitHub Release Notifier ローカルテスト')
    parser.add_argument('--test-mode', action='store_true', help='テストモード（1件のみ送信）')
    parser.add_argument('--since-hours', type=int, default=24, help='何時間前からの通知を取得するか（デフォルト: 24）')
    parser.add_argument('--dry-run', action='store_true', help='Slackに送信せずに表示のみ')
    args = parser.parse_args()

    print("=" * 70)
    print("GitHub Release Notifier - ローカルテスト")
    print("=" * 70)
    print()

    # 環境変数から設定を取得
    github_token = os.getenv("GITHUB_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    # 必須環境変数のチェック
    if not github_token:
        print("❌ エラー: GITHUB_TOKEN 環境変数が設定されていません")
        print("設定方法: export GITHUB_TOKEN='your_github_token'")
        sys.exit(1)
    if not openai_api_key:
        print("❌ エラー: OPENAI_API_KEY 環境変数が設定されていません")
        print("設定方法: export OPENAI_API_KEY='your_openai_api_key'")
        sys.exit(1)
    if not slack_webhook_url and not args.dry_run:
        print("❌ エラー: SLACK_WEBHOOK_URL 環境変数が設定されていません")
        print("設定方法: export SLACK_WEBHOOK_URL='your_slack_webhook_url'")
        print("または --dry-run オプションを使用してください")
        sys.exit(1)

    print("⚙️  設定:")
    print(f"  - テストモード: {args.test_mode}")
    print(f"  - 取得期間: 過去{args.since_hours}時間")
    print(f"  - OpenAIモデル: {openai_model}")
    print(f"  - Dry Run: {args.dry_run}")
    print()

    try:
        # クライアント初期化
        print("🔧 クライアント初期化中...")
        github_client = GitHubClient(github_token)
        llm_summarizer = LLMSummarizer(openai_api_key, openai_model)
        if not args.dry_run:
            slack_notifier = SlackNotifier(slack_webhook_url)
        print("✓ 初期化完了")
        print()

        # GitHub通知を取得
        print(f"🔍 GitHub通知を取得中（過去{args.since_hours}時間）...")
        notifications = github_client.get_notifications(since_hours=args.since_hours)
        print(f"✓ {len(notifications)} 件の通知を取得")
        print()

        # リリース通知のみをフィルタリング
        print("🔍 リリース通知をフィルタリング中...")
        release_notifications = github_client.filter_release_notifications(notifications)
        print(f"✓ {len(release_notifications)} 件のリリース通知を検出")
        print()

        if not release_notifications:
            print("📭 リリース通知はありません")
            return

        # テストモードは1件のみ、通常モードは古い順に処理
        release_notifications = order_releases(release_notifications, args.test_mode)
        if args.test_mode:
            print(f"⚠️  テストモード: {len(release_notifications)} 件のみ処理")
        else:
            print("📅 古い順に処理します")
        print()

        # 全てのリリースを並列で要約
        print("🔄 並列要約を開始...")
        summarization_results = summarize_releases_parallel(
            release_notifications=release_notifications,
            llm_summarizer=llm_summarizer,
            logger=_create_console_logger()
        )
        print()

        # 要約結果を古い順にSlackに送信
        sent_count = 0
        errors = []

        for idx, (release_data, summary, error_msg) in enumerate(summarization_results, 1):
            print("-" * 70)
            info = _extract_release_info(release_data)
            print(f"[{idx}/{len(summarization_results)}] {info.repository_name} {info.tag_name}")
            print()

            # 要約にエラーがあった場合
            if error_msg:
                errors.append(error_msg)
                print(f"  ✗ 要約エラー: {error_msg}")
                print()
                continue

            # 要約を表示
            print("  📝 要約:")
            for line in summary.split('\n'):
                print(f"    {line}")
            print()

            # Slackに送信
            if args.dry_run:
                print("  ⚠️  Dry Run: Slackへの送信をスキップ")
            else:
                try:
                    print("  📤 Slackに送信中...")
                    success = slack_notifier.send_release_notification(
                        repository=info.repository_name,
                        version=info.tag_name,
                        summary=summary,
                        release_url=info.release_url,
                        published_at=info.published_at
                    )

                    if success:
                        sent_count += 1
                        print("  ✓ Slack送信完了")
                    else:
                        error_msg = f"{info.repository_name} {info.tag_name}: Slack送信失敗"
                        errors.append(error_msg)
                        print("  ✗ Slack送信失敗")

                except Exception as e:
                    error_msg = f"{info.repository_name} {info.tag_name}: Slack error: {str(e)}"
                    errors.append(error_msg)
                    print(f"  ✗ Slackエラー: {e}")

            print()

        # 結果サマリー
        print("=" * 70)
        print("📊 実行結果:")
        print("=" * 70)
        print(f"  通知総数: {len(notifications)}")
        print(f"  リリース通知: {len(release_notifications)}")
        if args.dry_run:
            print(f"  処理済み: {len(release_notifications)}")
        else:
            print(f"  送信成功: {sent_count}")
        if errors:
            print(f"  エラー: {len(errors)}")
            for error in errors:
                print(f"    - {error}")
        print("=" * 70)

    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ 致命的エラー: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
