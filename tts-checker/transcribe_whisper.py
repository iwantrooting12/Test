"""OpenAI Whisper API 文字起こしモジュール。"""

import os
import time
from pathlib import Path

from openai import OpenAI


WHISPER_MAX_RETRIES = 3
WHISPER_REQUEST_DELAY = 0.5  # リクエスト間の待ち時間（秒）


def _transcribe_one(client: OpenAI, filepath: Path, lang: str) -> dict:
    """1ファイルの文字起こしを実行する（リトライ付き）。"""
    last_error = None
    for attempt in range(WHISPER_MAX_RETRIES):
        try:
            with open(filepath, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=lang,
                )
            time.sleep(WHISPER_REQUEST_DELAY)
            return {"filename": filepath.name, "transcript": response.text}
        except Exception as e:
            last_error = e
            if attempt < WHISPER_MAX_RETRIES - 1:
                wait = (2 ** attempt) * 2
                print(f"  {filepath.name}: エラー。{wait}秒待機中... (リトライ {attempt + 1}/{WHISPER_MAX_RETRIES})")
                time.sleep(wait)

    return {"filename": filepath.name, "transcript": f"[ERROR: {last_error}]"}


def transcribe_files(
    audio_files: list[Path], api_key: str, lang: str,
    progress_callback=None,
) -> list[dict]:
    """OpenAI Whisper APIで複数の音声ファイルを文字起こしする。

    Args:
        audio_files: 音声ファイルパスのリスト
        api_key: OpenAI APIキー
        lang: 言語コード (ja, en, ko, etc.)
        progress_callback: 進捗コールバック callback(done, total, filename)

    Returns:
        [{"filename": "01.wav", "transcript": "..."}, ...]
    """
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI APIキーが指定されていません。")

    client = OpenAI(api_key=api_key)
    total = len(audio_files)
    results = []

    for i, filepath in enumerate(audio_files):
        result = _transcribe_one(client, filepath, lang)
        results.append(result)
        if progress_callback:
            progress_callback(i + 1, total, result["filename"])

    return results
