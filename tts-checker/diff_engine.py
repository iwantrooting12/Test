"""文字単位diff比較エンジン。"""

import difflib
import re
import unicodedata

from config import STRIP_CHARS_FROM_MANUSCRIPT


def normalize(text: str, strip_chars: list[str] | None = None) -> str:
    """テキストを正規化する。

    1. 全角英数字 → 半角英数字
    2. 半角カナ → 全角カナ
    3. 原稿の除去文字を削除
    4. 連続する空白・改行 → 単一スペース
    5. strip
    """
    if strip_chars is None:
        strip_chars = STRIP_CHARS_FROM_MANUSCRIPT

    # NFKC正規化: 全角英数字→半角、半角カナ→全角 を一括処理
    text = unicodedata.normalize("NFKC", text)

    # 除去文字を削除
    for ch in strip_chars:
        # NFKC正規化後の文字も除去対象に
        ch_normalized = unicodedata.normalize("NFKC", ch)
        text = text.replace(ch, "")
        if ch_normalized != ch:
            text = text.replace(ch_normalized, "")

    # 連続する空白・改行 → 単一スペース
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def compute_diff(manuscript: str, transcript: str) -> list[dict]:
    """文字単位のdiffを実行する。

    Returns:
        [{"tag": "equal"|"replace"|"delete"|"insert",
          "manuscript_slice": str,
          "transcript_slice": str}, ...]
    """
    sm = difflib.SequenceMatcher(None, manuscript, transcript)
    opcodes = sm.get_opcodes()

    results = []
    for tag, i1, i2, j1, j2 in opcodes:
        results.append({
            "tag": tag,
            "manuscript_slice": manuscript[i1:i2],
            "transcript_slice": transcript[j1:j2],
        })
    return results


def match_ratio(manuscript: str, transcript: str) -> float:
    """一致率を計算する (0.0 ~ 1.0)。"""
    sm = difflib.SequenceMatcher(None, manuscript, transcript)
    return sm.ratio()
