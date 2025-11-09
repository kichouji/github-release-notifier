#!/usr/bin/env python3
"""
ローカルテストスクリプト
OCI Functionのロジックを fn invoke を使わずにローカルで実行します
"""

import os
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 同じディレクトリのモジュールをインポート
sys.path.insert(0, str(Path(__file__).parent))

from github_client import GitHubClient
from llm_summarizer import LLMSummarizer
from slack_notifier import SlackNotifier
from func import ReleaseInfo, _extract_release_info


def _summarize_single_release(
    release_data: dict,
    llm_summarizer: LLMSummarizer,
    openai_model: str,
    index: int,
    total: int
) -> tuple[dict, str, str]:
    """
    単一のリリースを要約（スレッドプール用）

    Args:
        release_data: リリースデータ（notification + release）
        llm_summarizer: LLM要約クライアント
        openai_model: 使用するOpenAIモデル名（未使用だがシグネチャ保持のため残す）
        index: インデックス（未使用だがシグネチャ保持のため残す）
        total: 総数（未使用だがシグネチャ保持のため残す）

    Returns:
        (リリースデータ, 要約, エラーメッセージ)
    """
    info = _extract_release_info(release_data)

    try:
        summary = llm_summarizer.summarize(
            repository=info.repository_name,
            version=info.tag_name,
            release_note=info.release_body
        )
        return (release_data, summary, None)

    except Exception as e:
        error_msg = f"{info.repository_name} {info.tag_name}: {str(e)}"
        return (release_data, None, error_msg)


def _summarize_all_releases_parallel(
    release_notifications: list,
    llm_summarizer: LLMSummarizer,
    openai_model: str
) -> list[tuple[dict, str, str]]:
    """
    全てのリリースを並列要約（ThreadPoolExecutor使用）

    Args:
        release_notifications: リリース通知リスト
        llm_summarizer: LLM要約クライアント
        openai_model: 使用するOpenAIモデル名

    Returns:
        [(リリースデータ, 要約, エラーメッセージ), ...]
    """
    print(f"🚀 Starting parallel summarization for {len(release_notifications)} releases")

    # 結果を格納する辞書（インデックスで順序を保持）
    results_dict = {}

    # ThreadPoolExecutorで並列実行
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 全てのタスクを投入
        future_to_index = {
            executor.submit(
                _summarize_single_release,
                release_data,
                llm_summarizer,
                openai_model,
                idx,
                len(release_notifications)
            ): idx
            for idx, release_data in enumerate(release_notifications, 1)
        }

        # 完了したタスクから結果を収集
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                result = future.result()
                results_dict[index] = result
                release_data, summary, error_msg = result
                info = _extract_release_info(release_data)

                if error_msg:
                    print(f"  [{index}/{len(release_notifications)}] Error: {info.repository_name} {info.tag_name}")
                else:
                    print(f"  [{index}/{len(release_notifications)}] Completed: {info.repository_name} {info.tag_name} ({len(summary)} chars)")
            except Exception as e:
                print(f"  [{index}/{len(release_notifications)}] Unexpected error: {e}")
                # エラーの場合は空の結果を格納
                results_dict[index] = (release_notifications[index-1], None, str(e))

    # インデックス順にソートして結果を返す
    results = [results_dict[i] for i in sorted(results_dict.keys())]
    print(f"✓ Completed parallel summarization for {len(release_notifications)} releases")
    print()

    return results


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
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
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

    print(f"⚙️  設定:")
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

        # テストモードの場合は1件のみに制限
        if args.test_mode:
            release_notifications = release_notifications[:1]
            print(f"⚠️  テストモード: {len(release_notifications)} 件のみ処理")
            print()
        else:
            # 通常モードの場合は古い順に処理（リストを逆順にする）
            release_notifications = release_notifications[::-1]
            print(f"📅 古い順に処理します")
            print()

        # 全てのリリースを並列で要約（ThreadPoolExecutor使用）
        print("🔄 並列要約を開始...")
        print()
        summarization_results = _summarize_all_releases_parallel(
            release_notifications=release_notifications,
            llm_summarizer=llm_summarizer,
            openai_model=openai_model
        )

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
