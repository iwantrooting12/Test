"""TTS音声チェックツール — CLIエントリポイント。"""

import argparse
import re
import sys
from pathlib import Path

from config import AUDIO_EXTENSIONS
from diff_engine import compute_diff, match_ratio, normalize
from manuscript_parser import parse_manuscript
from report_generator import generate_report
from transcribe import transcribe_files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TTS音声チェックツール")
    parser.add_argument("--manuscript", required=True, help="原稿ファイルパス (.docx / .xlsx / .txt)")
    parser.add_argument("--audio-dir", required=True, help="音声ファイルが入ったディレクトリ")
    parser.add_argument("--output", default="report.html", help="出力HTMLパス (デフォルト: report.html)")
    parser.add_argument("--lang", default="ja", help="音声の言語コード (デフォルト: ja)")
    parser.add_argument("--gladia-key", default="", help="Gladia APIキー (未指定なら環境変数 GLADIA_API_KEY)")
    parser.add_argument("--no-normalize", action="store_true", help="テキスト正規化をスキップ")
    return parser.parse_args(argv)


def collect_audio_files(audio_dir: str | Path) -> list[Path]:
    """音声ファイルを収集してソートする。"""
    audio_dir = Path(audio_dir)
    if not audio_dir.is_dir():
        raise FileNotFoundError(f"音声ディレクトリが見つかりません: {audio_dir}")
    files = [f for f in sorted(audio_dir.iterdir()) if f.suffix.lower() in AUDIO_EXTENSIONS]
    if not files:
        raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_dir}")
    return files


def _extract_number(filename: str) -> int | None:
    """ファイル名から先頭の数字を抽出する。"""
    match = re.search(r"(\d+)", filename)
    if match:
        return int(match.group(1))
    return None


def match_audio_to_entries(audio_files: list[Path], entries: list[dict]) -> list[dict]:
    """音声ファイルと原稿エントリを対応付ける。

    ファイル名から番号を抽出し、原稿エントリのidと一致させる。
    数字が抽出できない場合、ソート順で連番対応。
    """
    entry_map = {e["id"]: e for e in entries}
    pairs = []
    unmatched_audio = []

    for audio in audio_files:
        num = _extract_number(audio.stem)
        if num is not None and str(num) in entry_map:
            pairs.append({"audio": audio, "entry": entry_map[str(num)]})
        else:
            unmatched_audio.append(audio)

    # マッチしなかったファイルは順番で対応付け
    if unmatched_audio:
        matched_ids = {p["entry"]["id"] for p in pairs}
        remaining_entries = [e for e in entries if e["id"] not in matched_ids]
        for audio, entry in zip(unmatched_audio, remaining_entries):
            pairs.append({"audio": audio, "entry": entry})
            print(f"警告: {audio.name} → エントリ#{entry['id']} に順番で対応付け", file=sys.stderr)

        # 対応付けできなかった音声ファイル
        if len(unmatched_audio) > len(remaining_entries):
            for audio in unmatched_audio[len(remaining_entries):]:
                print(f"警告: {audio.name} に対応する原稿エントリがありません", file=sys.stderr)

    # audioのソート順を維持
    pairs.sort(key=lambda p: p["audio"].name)
    return pairs


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # 1. 原稿パース
    entries = parse_manuscript(args.manuscript)
    print(f"原稿エントリ数: {len(entries)}")

    # 2. 音声ファイル収集
    audio_files = collect_audio_files(args.audio_dir)
    print(f"音声ファイル数: {len(audio_files)}")

    # 3. 対応付け
    pairs = match_audio_to_entries(audio_files, entries)
    print(f"対応付け数: {len(pairs)}")

    # 4. 文字起こし (Gladia API)
    transcripts = transcribe_files(
        [p["audio"] for p in pairs],
        api_key=args.gladia_key,
        lang=args.lang,
    )

    # 5. diff比較
    results = []
    for pair, transcript in zip(pairs, transcripts):
        if args.no_normalize:
            m_text = pair["entry"]["text"]
            t_text = transcript["transcript"]
        else:
            m_text = normalize(pair["entry"]["text"])
            t_text = normalize(transcript["transcript"], strip_chars=[])

        diff = compute_diff(m_text, t_text)
        ratio = match_ratio(m_text, t_text)
        results.append({
            "filename": pair["audio"].name,
            "entry_id": pair["entry"]["id"],
            "manuscript_raw": pair["entry"]["text"],
            "transcript_raw": transcript["transcript"],
            "manuscript_normalized": m_text,
            "transcript_normalized": t_text,
            "diff": diff,
            "ratio": ratio,
        })

    # 6. HTMLレポート出力
    generate_report(results, args.output, args.manuscript)
    print(f"レポート出力: {args.output}")


if __name__ == "__main__":
    main()
