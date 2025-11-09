"""
GitHub Release 通知自動投稿 OCI Function
"""

import io
import json
import logging
import os
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from fdk import response

from github_client import GitHubClient
from llm_summarizer import LLMSummarizer
from slack_notifier import SlackNotifier


# リリース情報を保持する軽量データクラス
ReleaseInfo = namedtuple('ReleaseInfo', [
    'repository_name',
    'tag_name',
    'release_body',
    'release_url',
    'published_at'
])


def _extract_release_info(release_data: dict) -> ReleaseInfo:
    """
    リリースデータから必要な情報を抽出

    Args:
        release_data: リリースデータ（notification + release）

    Returns:
        ReleaseInfo: 抽出されたリリース情報
    """
    notification = release_data["notification"]
    release = release_data["release"]
    repository = notification["repository"]

    return ReleaseInfo(
        repository_name=repository.get("full_name", "Unknown"),
        tag_name=release.get("tag_name", "Unknown"),
        release_body=release.get("body", ""),
        release_url=release.get("html_url", ""),
        published_at=release.get("published_at", "")
    )


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
    logger,
    openai_model: str
) -> list[tuple[dict, str, str]]:
    """
    全てのリリースを並列要約（ThreadPoolExecutor使用）

    Args:
        release_notifications: リリース通知リスト
        llm_summarizer: LLM要約クライアント
        logger: ロガー
        openai_model: 使用するOpenAIモデル名

    Returns:
        [(リリースデータ, 要約, エラーメッセージ), ...]
    """
    logger.info(f"Starting parallel summarization for {len(release_notifications)} releases")

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
                    logger.error(f"  [{index}/{len(release_notifications)}] Error: {info.repository_name} {info.tag_name}")
                else:
                    logger.info(f"  [{index}/{len(release_notifications)}] Completed: {info.repository_name} {info.tag_name} ({len(summary)} chars)")
            except Exception as e:
                logger.error(f"  [{index}/{len(release_notifications)}] Unexpected error: {e}")
                # エラーの場合は空の結果を格納
                results_dict[index] = (release_notifications[index-1], None, str(e))

    # インデックス順にソートして結果を返す
    results = [results_dict[i] for i in sorted(results_dict.keys())]
    logger.info(f"Completed parallel summarization for {len(release_notifications)} releases")

    return results


def handler(ctx, data: io.BytesIO = None):
    """
    OCI Function ハンドラー

    環境変数:
        GITHUB_TOKEN: GitHub Personal Access Token
        OPENAI_API_KEY: OpenAI API Key
        OPENAI_MODEL: OpenAI モデル名（デフォルト: gpt-5-mini）
        SLACK_WEBHOOK_URL: Slack Incoming Webhook URL

    ペイロード（JSON）:
        test_mode: true の場合、1件のみ送信（デフォルト: false）
        since_hours: 何時間前からの通知を取得するか（デフォルト: 24）
    """
    logger = logging.getLogger()
    logger.info("GitHub Release Notifier started")

    # 環境変数から設定を取得
    github_token = os.getenv("GITHUB_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    # 必須環境変数のチェック
    if not github_token:
        return error_response(ctx, "GITHUB_TOKEN environment variable is not set")
    if not openai_api_key:
        return error_response(ctx, "OPENAI_API_KEY environment variable is not set")
    if not slack_webhook_url:
        return error_response(ctx, "SLACK_WEBHOOK_URL environment variable is not set")

    # ペイロードから設定を取得
    test_mode = False
    since_hours = 24

    try:
        if data and data.getvalue():
            body = json.loads(data.getvalue())
            test_mode = body.get("test_mode", False)
            since_hours = body.get("since_hours", 24)
            logger.info(f"Payload: test_mode={test_mode}, since_hours={since_hours}")
    except (Exception, ValueError) as ex:
        logger.warning(f"Error parsing payload (using defaults): {ex}")

    try:
        # クライアント初期化
        github_client = GitHubClient(github_token)
        llm_summarizer = LLMSummarizer(openai_api_key, openai_model)
        slack_notifier = SlackNotifier(slack_webhook_url)

        # GitHub通知を取得
        logger.info(f"Fetching notifications from the last {since_hours} hours")
        notifications = github_client.get_notifications(since_hours=since_hours)
        logger.info(f"Found {len(notifications)} notifications")

        # リリース通知のみをフィルタリング
        release_notifications = github_client.filter_release_notifications(notifications)
        logger.info(f"Found {len(release_notifications)} release notifications")

        if not release_notifications:
            return success_response(ctx, {
                "message": "No release notifications found",
                "notifications_total": len(notifications),
                "release_notifications": 0,
                "sent": 0
            })

        # テストモードの場合は1件のみに制限
        if test_mode:
            release_notifications = release_notifications[:1]
            logger.info("Test mode: limiting to 1 notification")
        else:
            # 通常モードの場合は古い順に処理（リストを逆順にする）
            release_notifications = release_notifications[::-1]
            logger.info("Processing notifications in chronological order (oldest first)")

        # 全てのリリースを並列で要約（ThreadPoolExecutor使用）
        logger.info("Starting parallel summarization...")
        summarization_results = _summarize_all_releases_parallel(
            release_notifications=release_notifications,
            llm_summarizer=llm_summarizer,
            logger=logger,
            openai_model=openai_model
        )
        logger.info("Parallel summarization completed")

        # 要約結果を古い順にSlackに送信
        sent_count = 0
        errors = []

        for idx, (release_data, summary, error_msg) in enumerate(summarization_results, 1):
            info = _extract_release_info(release_data)
            logger.info(f"[{idx}/{len(summarization_results)}] Sending to Slack: {info.repository_name} {info.tag_name}")

            # 要約にエラーがあった場合
            if error_msg:
                errors.append(error_msg)
                logger.error(f"  ✗ Summarization failed: {error_msg}")
                continue

            # Slackに送信
            try:
                logger.info("  Sending to Slack...")
                success = slack_notifier.send_release_notification(
                    repository=info.repository_name,
                    version=info.tag_name,
                    summary=summary,
                    release_url=info.release_url,
                    published_at=info.published_at
                )

                if success:
                    sent_count += 1
                    logger.info(f"  ✓ Successfully sent to Slack")
                else:
                    error_msg = f"{info.repository_name} {info.tag_name}: Slack send failed"
                    errors.append(error_msg)
                    logger.error(f"  ✗ Failed to send to Slack")

            except Exception as e:
                error_msg = f"{info.repository_name} {info.tag_name}: Slack error: {str(e)}"
                errors.append(error_msg)
                logger.error(f"  ✗ Error sending to Slack: {e}")

        # 結果を返す
        result = {
            "message": "GitHub Release notifications processed",
            "test_mode": test_mode,
            "since_hours": since_hours,
            "notifications_total": len(notifications),
            "release_notifications": len(release_notifications),
            "sent": sent_count,
            "errors": errors if errors else None
        }

        logger.info(f"Completed: {sent_count}/{len(release_notifications)} sent")
        return success_response(ctx, result)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return error_response(ctx, str(e))


def success_response(ctx, data: dict):
    """成功レスポンスを返す"""
    return response.Response(
        ctx,
        response_data=json.dumps(data, ensure_ascii=False, indent=2),
        headers={"Content-Type": "application/json"}
    )


def error_response(ctx, error_message: str):
    """エラーレスポンスを返す"""
    return response.Response(
        ctx,
        response_data=json.dumps({
            "error": error_message
        }, ensure_ascii=False),
        headers={"Content-Type": "application/json"},
        status_code=500
    )
