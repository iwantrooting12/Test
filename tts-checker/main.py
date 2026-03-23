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
    files = [f for f in audio_dir.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS]
    def _sort_key(f):
        num = _extract_number(f.stem)
        return (num if num is not None else float("inf"), f.name)
    files.sort(key=_sort_key)
    if not files:
        raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_dir}")
    return files


def _extract_number(filename: str) -> int | None:
    """ファイル名から先頭の数字を抽出する。"""
    match = re.search(r"(\d+)", filename)
    if match:
        return int(match.group(1))
    return None


def _extract_artist_name(text: str) -> str:
    """エントリテキストから作家名を抽出する（最初の「。」の前）。"""
    # "桂ゆき。，東京市..." → "桂ゆき"
    # "桂ゆき，作、《...》。，..." → "桂ゆき"
    name = text.split("。")[0].split("，")[0].strip()
    # 全角・半角スペースを除去して正規化
    return name


def _normalize_for_match(s: str) -> str:
    """マッチング用にテキストを正規化する。"""
    return s.replace(" ", "").replace("\u3000", "").replace("・", "").replace("=", "＝").lower()


def match_audio_to_entries(audio_files: list[Path], entries: list[dict]) -> list[dict]:
    """音声ファイルと原稿エントリを対応付ける。

    原稿が自動採番（番号行なし）の場合: 作家名マッチ → 順序マッチ
    原稿が明示的番号の場合: 番号マッチ → 順序マッチ
    """
    is_auto_numbered = any(e.get("auto_numbered") for e in entries)

    if is_auto_numbered:
        return _match_by_name_and_sequence(audio_files, entries)
    else:
        return _match_by_number(audio_files, entries)


def _match_by_name_and_sequence(audio_files: list[Path], entries: list[dict]) -> list[dict]:
    """作家名でマッチし、残りを順序で対応付ける。"""
    pairs = []
    matched_audio = set()
    matched_entry_ids = set()

    # 1. 作家名マッチ: ファイル名に作家名が含まれるケース
    #    例: JP-パウル・クレー_略歴.mp3 → エントリ「パウル・クレー。，ベルン近郊...」
    for entry in entries:
        artist_name = _extract_artist_name(entry["text"])
        if not artist_name or len(artist_name) < 2:
            continue
        name_norm = _normalize_for_match(artist_name)
        for audio in audio_files:
            if id(audio) in matched_audio:
                continue
            stem_norm = _normalize_for_match(audio.stem)
            if name_norm in stem_norm:
                pairs.append({"audio": audio, "entry": entry})
                matched_audio.add(id(audio))
                matched_entry_ids.add(entry["id"])
                print(f"名前マッチ: {audio.name} → {artist_name}", file=sys.stderr)
                break

    # 2. 残りを順序で対応付け（数値順の音声 ↔ 残りのエントリ）
    #    同一番号のファイル（JP-15_①, JP-15_②等）は同じエントリにマッチさせる
    remaining_audio = [a for a in audio_files if id(a) not in matched_audio]
    remaining_entries = [e for e in entries if e["id"] not in matched_entry_ids]

    def _audio_sort_key(f):
        num = _extract_number(f.stem)
        return (num if num is not None else float("inf"), f.name)
    remaining_audio.sort(key=_audio_sort_key)

    # 同一番号のファイルをグループ化
    audio_groups: list[list[Path]] = []
    for audio in remaining_audio:
        num = _extract_number(audio.stem)
        if audio_groups and num is not None and _extract_number(audio_groups[-1][0].stem) == num:
            audio_groups[-1].append(audio)
        else:
            audio_groups.append([audio])

    for group, entry in zip(audio_groups, remaining_entries):
        for audio in group:
            pairs.append({"audio": audio, "entry": entry})

    # 対応付けできなかった音声ファイル
    if len(audio_groups) > len(remaining_entries):
        for group in audio_groups[len(remaining_entries):]:
            for audio in group:
                print(f"警告: {audio.name} に対応する原稿エントリがありません", file=sys.stderr)

    # audioを数値順でソート
    def _pair_sort_key(p):
        num = _extract_number(p["audio"].stem)
        return (num if num is not None else float("inf"), p["audio"].name)
    pairs.sort(key=_pair_sort_key)
    return pairs


def _match_by_number(audio_files: list[Path], entries: list[dict]) -> list[dict]:
    """番号でマッチし、残りを順序で対応付ける（明示的番号ありの原稿用）。"""
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

    # audioを数値順でソート
    def _pair_sort_key(p):
        num = _extract_number(p["audio"].stem)
        return (num if num is not None else float("inf"), p["audio"].name)
    pairs.sort(key=_pair_sort_key)
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
