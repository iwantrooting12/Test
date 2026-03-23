"""Faster Whisper ローカル文字起こしモジュール。"""

import os
import platform
import site
from pathlib import Path

# Windows: CUDA DLLのパスを通す（site-packages内のnvidiaライブラリ）
if platform.system() == "Windows":
    import importlib.util
    _nvidia_spec = importlib.util.find_spec("nvidia")
    _search_paths = []
    if _nvidia_spec and _nvidia_spec.submodule_search_locations:
        _search_paths = list(_nvidia_spec.submodule_search_locations)
    else:
        for site_dir in site.getsitepackages():
            _candidate = os.path.join(site_dir, "nvidia")
            if os.path.isdir(_candidate):
                _search_paths.append(_candidate)
    for nvidia_dir in _search_paths:
        if os.path.isdir(nvidia_dir):
            for lib_name in os.listdir(nvidia_dir):
                dll_dir = os.path.join(nvidia_dir, lib_name, "bin")
                if os.path.isdir(dll_dir):
                    os.add_dll_directory(dll_dir)

from faster_whisper import BatchedInferencePipeline, WhisperModel

# large-v3-turbo: large-v3と同等精度で高速
WHISPER_MODEL = "large-v3-turbo"
BATCH_SIZE = 16


def transcribe_files(
    audio_files: list[Path], api_key: str, lang: str,
    progress_callback=None,
) -> list[dict]:
    """Faster Whisperで複数の音声ファイルをローカルで文字起こしする。

    Args:
        audio_files: 音声ファイルパスのリスト
        api_key: 未使用（互換性のため残す）
        lang: 言語コード (ja, en, ko, etc.)
        progress_callback: 進捗コールバック callback(done, total, filename)

    Returns:
        [{"filename": "01.wav", "transcript": "..."}, ...]
    """
    print(f"Faster Whisper モデル読み込み中: {WHISPER_MODEL}")
    model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
    batched_model = BatchedInferencePipeline(model=model)

    total = len(audio_files)
    results = []

    for i, filepath in enumerate(audio_files):
        try:
            segments, _info = batched_model.transcribe(
                str(filepath),
                language=lang,
                batch_size=BATCH_SIZE,
                vad_filter=True,
            )
            transcript = "".join(seg.text for seg in segments)
            result = {"filename": filepath.name, "transcript": transcript}
        except Exception as e:
            print(f"  {filepath.name}: エラー — {e}")
            result = {"filename": filepath.name, "transcript": f"[ERROR: {e}]"}

        results.append(result)
        if progress_callback:
            progress_callback(i + 1, total, result["filename"])

    return results
