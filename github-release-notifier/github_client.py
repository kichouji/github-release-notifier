"""
GitHub Notifications API クライアント
"""

import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional


class GitHubClient:
    """GitHub API操作クライアント"""

    def __init__(self, token: str):
        """
        初期化

        Args:
            token: GitHub Personal Access Token
        """
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def get_notifications(self, since_hours: int = 24) -> List[Dict[str, Any]]:
        """
        指定時間内の通知を取得

        Args:
            since_hours: 何時間前からの通知を取得するか

        Returns:
            通知のリスト
        """
        since_time = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        since_str = since_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{self.base_url}/notifications"
        params = {
            "all": "true",
            "since": since_str,
            "per_page": 100
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"GitHub API request failed: {e}")

    def get_release_details(self, release_url: str) -> Optional[Dict[str, Any]]:
        """
        リリース詳細を取得

        Args:
            release_url: リリースAPIのURL

        Returns:
            リリース詳細（取得失敗時はNone）
        """
        try:
            response = requests.get(release_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            # リリース詳細の取得に失敗してもスキップして処理を継続
            return None

    def filter_release_notifications(self, notifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        リリース通知のみをフィルタリング

        Args:
            notifications: 通知のリスト

        Returns:
            リリース通知のリスト（詳細情報付き）
        """
        release_notifications = []

        for notification in notifications:
            subject = notification.get("subject", {})
            subject_type = subject.get("type")

            # リリース通知のみを対象
            if subject_type == "Release":
                # リリース詳細を取得
                release_url = subject.get("url")
                if release_url:
                    release_details = self.get_release_details(release_url)
                    if release_details:
                        # 通知とリリース詳細を結合
                        release_notifications.append({
                            "notification": notification,
                            "release": release_details
                        })

        return release_notifications
