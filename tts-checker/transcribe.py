"""Gladia API V2 pre-recorded 文字起こしモジュール。"""

import asyncio
import os
import time
from pathlib import Path

import aiohttp

from config import (
    GLADIA_API_BASE,
    GLADIA_MAX_CONCURRENT,
    GLADIA_MAX_RETRIES,
    GLADIA_POLL_INTERVAL,
    GLADIA_POLL_TIMEOUT,
    GLADIA_REQUEST_DELAY,
)


async def _upload_audio(session: aiohttp.ClientSession, filepath: Path, api_key: str) -> str:
    """音声ファイルをGladiaにアップロードし、audio_urlを返す。"""
    url = f"{GLADIA_API_BASE}/upload"
    headers = {"x-gladia-key": api_key}

    data = aiohttp.FormData()
    data.add_field("audio", open(filepath, "rb"), filename=filepath.name)

    async with session.post(url, headers=headers, data=data) as resp:
        resp.raise_for_status()
        result = await resp.json()
        return result["audio_url"]


async def _request_transcription(
    session: aiohttp.ClientSession, audio_url: str, api_key: str, lang: str
) -> str:
    """文字起こしリクエストを送信し、result_urlを返す。"""
    url = f"{GLADIA_API_BASE}/pre-recorded"
    headers = {
        "x-gladia-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "audio_url": audio_url,
        "language": lang,
        "detect_language": False,
    }

    async with session.post(url, headers=headers, json=payload) as resp:
        resp.raise_for_status()
        result = await resp.json()
        return result["result_url"]


async def _poll_result(session: aiohttp.ClientSession, result_url: str, api_key: str) -> str:
    """ポーリングで文字起こし結果を取得する。"""
    headers = {"x-gladia-key": api_key}
    start = time.monotonic()

    while True:
        async with session.get(result_url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if data.get("status") == "done":
            return data["result"]["transcription"]["full_transcript"]

        if time.monotonic() - start > GLADIA_POLL_TIMEOUT:
            raise TimeoutError(f"文字起こしタイムアウト ({GLADIA_POLL_TIMEOUT}秒)")

        await asyncio.sleep(GLADIA_POLL_INTERVAL)


async def _transcribe_one(
    session: aiohttp.ClientSession,
    filepath: Path,
    api_key: str,
    lang: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """1ファイルの文字起こしを実行する（リトライ付き）。"""
    async with semaphore:
        last_error = None
        for attempt in range(GLADIA_MAX_RETRIES):
            try:
                audio_url = await _upload_audio(session, filepath, api_key)
                result_url = await _request_transcription(session, audio_url, api_key, lang)
                transcript = await _poll_result(session, result_url, api_key)
                await asyncio.sleep(GLADIA_REQUEST_DELAY)
                return {"filename": filepath.name, "transcript": transcript}
            except aiohttp.ClientResponseError as e:
                last_error = e
                if e.status == 429:
                    wait = (2 ** attempt) * 5
                    print(f"  [429] {filepath.name}: レート制限。{wait}秒待機中... (リトライ {attempt + 1}/{GLADIA_MAX_RETRIES})")
                    await asyncio.sleep(wait)
                elif attempt < GLADIA_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                if attempt < GLADIA_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)

        return {"filename": filepath.name, "transcript": f"[ERROR: {last_error}]"}


async def transcribe_files_async(
    audio_files: list[Path], api_key: str, lang: str
) -> list[dict]:
    """複数の音声ファイルを並列で文字起こしする。

    Args:
        audio_files: 音声ファイルパスのリスト
        api_key: Gladia APIキー
        lang: 言語コード (ja, en, ko, etc.)

    Returns:
        [{"filename": "01.wav", "transcript": "..."}, ...]
    """
    semaphore = asyncio.Semaphore(GLADIA_MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        tasks = [
            _transcribe_one(session, f, api_key, lang, semaphore)
            for f in audio_files
        ]
        return await asyncio.gather(*tasks)


def transcribe_files(audio_files: list[Path], api_key: str, lang: str) -> list[dict]:
    """同期インターフェース。"""
    if not api_key:
        api_key = os.environ.get("GLADIA_API_KEY", "")
    if not api_key:
        raise ValueError("Gladia APIキーが指定されていません。--gladia-key または環境変数 GLADIA_API_KEY を設定してください。")
    return asyncio.run(transcribe_files_async(audio_files, api_key, lang))
