"""
LLM要約モジュール
"""

import os
from openai import OpenAI


class LLMSummarizer:
    """OpenAI APIを使用したリリースノート要約"""

    def __init__(self, api_key: str, model_name: str = "gpt-5-mini", temperature: float = 0.3):
        """
        初期化

        Args:
            api_key: OpenAI API Key
            model_name: 使用するモデル名
            temperature: モデルの温度パラメータ
        """
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.system_prompt = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """
        プロンプトテンプレートをファイルから読み込み

        Returns:
            プロンプトテンプレート文字列
        """
        # このファイルと同じディレクトリからテンプレートを読み込む
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(current_dir, "prompt_template.txt")

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise Exception(f"Prompt template file not found: {template_path}")

    def _build_user_message(self, repository: str, version: str, release_note: str) -> str:
        """
        ユーザーメッセージを構築

        Args:
            repository: リポジトリ名
            version: バージョン
            release_note: リリースノート本文

        Returns:
            構築されたユーザーメッセージ
        """
        return f"""リポジトリ: {repository}
バージョン: {version}

リリースノート:
{release_note}

上記のリリースノートを要約してください。"""

    def _build_api_params(self, user_message: str) -> dict:
        """
        OpenAI APIパラメータを構築

        Args:
            user_message: ユーザーメッセージ

        Returns:
            APIパラメータ辞書

        Note:
            GPT-5シリーズ（gpt-5, gpt-5-mini, gpt-5-nano）は推論モデルで、
            内部推論にトークンを消費するため、max_tokensを設定しない。
            また、temperatureはデフォルト値（1）のみサポート。
        """
        api_params = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message}
            ]
        }

        # GPT-5シリーズ以外の場合のみtemperatureを設定
        if not self.model_name.startswith("gpt-5"):
            api_params["temperature"] = self.temperature

        return api_params

    def summarize(self, repository: str, version: str, release_note: str) -> str:
        """
        リリースノートを要約

        Args:
            repository: リポジトリ名
            version: バージョン
            release_note: リリースノート本文

        Returns:
            要約されたテキスト
        """
        try:
            user_message = self._build_user_message(repository, version, release_note)
            api_params = self._build_api_params(user_message)
            response = self.client.chat.completions.create(**api_params)

            summary = response.choices[0].message.content
            return summary if summary else ""

        except Exception as e:
            raise Exception(f"LLM summarization failed: {e}")
