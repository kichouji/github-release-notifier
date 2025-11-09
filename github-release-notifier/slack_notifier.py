"""
Slack通知モジュール
"""

import os
import json
import requests
from typing import Dict, Any, Optional


class SlackNotifier:
    """Slack通知クライアント"""

    def __init__(self, webhook_url: str):
        """
        初期化

        Args:
            webhook_url: Slack Incoming Webhook URL
        """
        self.webhook_url = webhook_url

    def send_simple_message(self, message: str) -> bool:
        """
        シンプルなメッセージを送信

        Args:
            message: 送信するメッセージ

        Returns:
            送信成功フラグ
        """
        payload = {
            "text": message
        }

        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return response.text == "ok"
        except requests.exceptions.RequestException as e:
            raise Exception(f"Slack notification failed: {e}")

    def send_release_notification(
        self,
        repository: str,
        version: str,
        summary: str,
        release_url: str,
        published_at: Optional[str] = None
    ) -> bool:
        """
        リリース通知を送信（プレーンテキスト形式）

        Args:
            repository: リポジトリ名
            version: バージョン
            summary: 要約
            release_url: リリースページのURL
            published_at: 公開日時

        Returns:
            送信成功フラグ
        """
        # プレーンテキストメッセージを構築
        message_parts = [
            f"🆕 {repository} {version} がリリースされました！",
            "",
            f"リポジトリ: {repository}",
            f"バージョン: {version}"
        ]

        # 公開日時がある場合は追加
        if published_at:
            message_parts.append(f"リリース日: {published_at[:10]}")

        message_parts.extend([
            "",
            "📝 主な変更点:",
            summary,
            "",
            f"リリースノート: {release_url}",
            "-"
        ])

        message = "\n".join(message_parts)

        payload = {
            "text": message
        }

        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return response.text == "ok"
        except requests.exceptions.RequestException as e:
            raise Exception(f"Slack notification failed: {e}")
