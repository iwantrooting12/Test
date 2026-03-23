# TTS音声チェックツール 仕様書

## 概要

Azure TTSで生成した多言語AI音声の品質チェックツール。
音声ファイルを文字起こしし、原稿テキストと文字単位で比較して、
固有名詞の誤読・単語の欠落・追加などのクリティカルな誤りを検出する。

## ディレクトリ構成

```
tts-checker/
├── main.py              # CLIエントリポイント
├── transcribe.py        # Gladia API 文字起こし
├── manuscript_parser.py # 原稿パーサー（docx/xlsx/txt）
├── diff_engine.py       # 文字単位diff比較
├── report_generator.py  # HTMLレポート出力
├── config.py            # 設定・定数
├── requirements.txt
└── README.md
```

## 実行方法

```bash
python main.py \
  --manuscript manuscript.docx \
  --audio-dir ./audio_files/ \
  --output report.html \
  --lang ja
```

### 引数

| 引数 | 必須 | 説明 |
|------|------|------|
| `--manuscript` | ○ | 原稿ファイルパス（.docx / .xlsx / .txt） |
| `--audio-dir` | ○ | 音声ファイルが入ったディレクトリ |
| `--output` | △ | 出力HTMLパス（デフォルト: `report.html`） |
| `--lang` | △ | 音声の言語コード（デフォルト: `ja`）。Gladia APIに渡す |
| `--gladia-key` | △ | Gladia APIキー。未指定なら環境変数 `GLADIA_API_KEY` を参照 |
| `--no-normalize` | △ | テキスト正規化をスキップ |

---

## モジュール仕様

### 1. `manuscript_parser.py` — 原稿パーサー

#### 役割
原稿ファイルを読み込み、番号付きエントリのリストを返す。

#### 入力
ファイルパス（.docx / .xlsx / .txt）

#### 出力
```python
list[dict]  # 例: [{"id": "1", "text": "桂ゆき，作、《婦人の日》。..."}, ...]
```

#### パースロジック

**番号付き原稿の検出**（今回の添付ファイルのような形式）:
- テキストを行単位で分割
- `^\d+$` にマッチする行を番号行として検出
- 次の番号行（または末尾）までのテキストを、その番号のエントリとする
- 空行は無視

**番号なし原稿の場合**:
- 空行で区切られたブロックを1エントリとする
- idは連番（"1", "2", ...）を自動付与

**docxの読み取り**:
- `python-docx` でパラグラフを取得
- pandocが使えればpandocでplaintext抽出してもよい

**xlsxの読み取り**:
- `openpyxl` で読む
- 1列目=番号、2列目=テキスト を想定
- または1列のみの場合は上記の番号検出ロジックを適用

**txtの読み取り**:
- UTF-8で読み、上記の番号検出ロジックを適用

---

### 2. `transcribe.py` — Gladia文字起こし

#### 役割
音声ファイル群をGladia APIで文字起こしする。

#### Gladia API フロー（V2 pre-recorded）

**Step 1: アップロード**
```
POST https://api.gladia.io/v2/upload
Header: x-gladia-key: {API_KEY}
Header: Content-Type: multipart/form-data
Body: audio=@{filepath}

Response: {"audio_url": "https://api.gladia.io/file/{id}", ...}
```

**Step 2: 文字起こしリクエスト**
```
POST https://api.gladia.io/v2/pre-recorded
Header: x-gladia-key: {API_KEY}
Header: Content-Type: application/json
Body: {
  "audio_url": "{audio_url from step1}",
  "language": "{lang}",
  "detect_language": false
}

Response: {"id": "...", "result_url": "https://api.gladia.io/v2/pre-recorded/{id}"}
```

**Step 3: 結果取得（ポーリング）**
```
GET {result_url}
Header: x-gladia-key: {API_KEY}

ポーリング間隔: 3秒
終了条件: status == "done"
タイムアウト: 300秒

結果のテキスト: result.transcription.full_transcript
```

#### 入出力

```python
# 入力
audio_files: list[Path]  # 音声ファイルパスのリスト
api_key: str
lang: str  # 言語コード (ja, en, ko, th, vi, pt, nl, ...)

# 出力
list[dict]  # [{"filename": "01.wav", "transcript": "桂ゆき作..."}, ...]
```

#### 注意点
- 並列処理: `asyncio` + `aiohttp` で最大5並列でアップロード・文字起こしする
  （Gladiaのレート制限を考慮して抑えめにする）
- エラー時はリトライ3回、それでもダメなら transcript に "[ERROR: {reason}]" を入れてスキップ
- 対応音声フォーマット: wav, mp3, m4a, flac, ogg, aac（Gladiaが対応するもの全般）

---

### 3. `diff_engine.py` — 文字単位diff比較

#### 役割
原稿テキストと文字起こしテキストを文字単位で比較し、差分を返す。

#### テキスト正規化（比較前処理）

以下を適用してからdiffする。これにより表記揺れによるノイズを除去する。

```python
def normalize(text: str) -> str:
    # 1. 全角英数字 → 半角英数字
    # 2. 半角カナ → 全角カナ
    # 3. 連続する空白・改行 → 単一スペース
    # 4. 句読点の正規化: ，→、（全角カンマ→読点）は行わない
    #    ※ 原稿で「，」が意味的に使われている場合がある
    # 5. strip
    return normalized_text
```

**重要: 原稿のカンマ「，」について**
添付サンプルの原稿では「，」が読みの区切り（ポーズ位置の指示）として使われている。
これはTTSの読み上げ指示であり、音声には読まれない。
→ **正規化時に「，」を削除する**。同様に読み上げに影響しない記号も削除:
- 「，」（全角カンマ）→ 削除
- 「《》」（二重山括弧）→ 削除
- その他、原稿によってカスタマイズ可能にする（config.pyで定義）

```python
# config.py
STRIP_CHARS_FROM_MANUSCRIPT = ["，", "《", "》"]
```

#### diffロジック

```python
import difflib

def compute_diff(manuscript: str, transcript: str) -> list[dict]:
    """
    文字単位のdiffを実行。
    
    Returns:
        list of {"tag": "equal"|"replace"|"delete"|"insert",
                 "manuscript_slice": str,
                 "transcript_slice": str}
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
```

#### 一致率の計算

```python
def match_ratio(manuscript: str, transcript: str) -> float:
    sm = difflib.SequenceMatcher(None, manuscript, transcript)
    return sm.ratio()  # 0.0 ~ 1.0
```

---

### 4. `report_generator.py` — HTMLレポート出力

#### 役割
diff結果をHTMLレポートとして出力する。

#### レイアウト

```
┌──────────────────────────────────────────────────────────────┐
│  TTS音声チェックレポート                                       │
│  生成日時: 2025-03-23 15:00:00                                │
│  原稿: MiyagiMuseumofArt_jp__fb.docx                          │
│  音声ファイル数: 27                                            │
│  全体一致率: 96.3%                                             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ■ サマリーテーブル                                            │
│  ┌──────────┬──────────┬────────┐                              │
│  │ファイル名 │ 一致率   │ ステータス│                            │
│  ├──────────┼──────────┼────────┤                              │
│  │ 01.wav   │  98.5%   │  ⚠ 要確認 │                          │
│  │ 02.wav   │ 100.0%   │  ✓ OK    │                           │
│  │ 03.wav   │  85.2%   │  ✗ 要修正 │                           │
│  └──────────┴──────────┴────────┘                              │
│                                                               │
│  ■ 詳細（各ファイル）                                          │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ #1 — 01.wav （一致率: 98.5%）                              │ │
│  │                                                           │ │
│  │ [文字起こし]                                               │ │
│  │ 桂ゆき作婦人の日。女性の溌溂としたポーズと表情には...       │ │
│  │                           ^^^^                            │ │
│  │ [原稿]                                                    │ │
│  │ 桂ゆき作婦人の日。女性の溌剌としたポーズと表情には...       │ │
│  │                           ^^^^                            │ │
│  │                                                           │ │
│  │ ▼ 差分一覧                                                │ │
│  │  - 位置 24: 原稿「溌剌」→ 文字起こし「溌溂」              │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

#### 差分マーキングの方法

HTMLの `<span>` タグで色分け:
- `replace`: 原稿側＝赤背景、文字起こし側＝赤背景
- `delete`: 原稿側＝黄色背景（文字起こしに欠落）
- `insert`: 文字起こし側＝青背景（原稿にない追加）
- `equal`: 装飾なし

```html
<!-- replace の例 -->
<span class="diff-replace">溌溂</span>

<!-- CSS -->
.diff-replace { background-color: #ffcccc; font-weight: bold; }
.diff-delete  { background-color: #fff3cd; text-decoration: line-through; }
.diff-insert  { background-color: #cce5ff; font-weight: bold; }
```

#### ステータス判定

| 一致率 | ステータス | 色 |
|--------|------------|-----|
| >= 99% | ✓ OK | 緑 |
| >= 95% | ⚠ 要確認 | 黄 |
| < 95%  | ✗ 要修正 | 赤 |

閾値は `config.py` でカスタマイズ可能にする。

---

### 5. `config.py` — 設定

```python
# テキスト正規化時に原稿から除去する文字
STRIP_CHARS_FROM_MANUSCRIPT = ["，", "《", "》"]

# ステータス判定閾値
THRESHOLD_OK = 0.99       # 99%以上 → OK
THRESHOLD_WARNING = 0.95  # 95%以上 → 要確認、未満 → 要修正

# Gladia API
GLADIA_API_BASE = "https://api.gladia.io/v2"
GLADIA_POLL_INTERVAL = 3      # 秒
GLADIA_POLL_TIMEOUT = 300     # 秒
GLADIA_MAX_CONCURRENT = 5     # 並列数
GLADIA_MAX_RETRIES = 3

# 音声ファイル拡張子
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
```

---

### 6. `main.py` — メインフロー

```python
def main():
    args = parse_args()
    
    # 1. 原稿パース
    entries = parse_manuscript(args.manuscript)
    print(f"原稿エントリ数: {len(entries)}")
    
    # 2. 音声ファイル収集・ソート
    audio_files = collect_audio_files(args.audio_dir)
    print(f"音声ファイル数: {len(audio_files)}")
    
    # 3. ファイル名から番号を抽出し、原稿エントリと対応付け
    pairs = match_audio_to_entries(audio_files, entries)
    # 対応付けできなかったファイルは警告表示
    
    # 4. 文字起こし（Gladia API）
    transcripts = transcribe_files(
        [p["audio"] for p in pairs],
        api_key=args.gladia_key,
        lang=args.lang
    )
    
    # 5. diff比較
    results = []
    for pair, transcript in zip(pairs, transcripts):
        manuscript_text = normalize(pair["entry"]["text"])
        transcript_text = normalize(transcript["transcript"])
        diff = compute_diff(manuscript_text, transcript_text)
        ratio = match_ratio(manuscript_text, transcript_text)
        results.append({
            "filename": pair["audio"].name,
            "entry_id": pair["entry"]["id"],
            "manuscript_raw": pair["entry"]["text"],
            "transcript_raw": transcript["transcript"],
            "manuscript_normalized": manuscript_text,
            "transcript_normalized": transcript_text,
            "diff": diff,
            "ratio": ratio,
        })
    
    # 6. HTMLレポート出力
    generate_report(results, args.output, args.manuscript)
    print(f"レポート出力: {args.output}")
```

#### 音声ファイルと原稿の対応付けロジック

```python
def match_audio_to_entries(audio_files, entries):
    """
    ファイル名から番号を抽出して原稿エントリと対応付ける。
    
    対応ルール:
    1. ファイル名の先頭の数字を抽出（例: "01.wav" → 1, "track_03.mp3" → 3）
    2. 原稿エントリのidと一致するものを対応付け
    3. 数字が抽出できない場合、ファイル名のソート順で連番対応
    """
```

---

## 依存パッケージ（requirements.txt）

```
python-docx>=0.8.11
openpyxl>=3.1.0
aiohttp>=3.9.0
Jinja2>=3.1.0
```

※ Jinja2はHTMLテンプレート生成に使用。
※ `difflib` は標準ライブラリ。

---

## 補足: 今後の拡張候補

1. **Whisper / ElevenLabs Scribe対応**: transcribe.pyにバックエンド切替を追加
2. **Excel出力オプション**: openpyxlのRichTextで差分カラー出力
3. **イントネーション検出**: 音声のピッチ分析（praat-parselmouth等）で
   アクセント異常を検出する機能（将来的に別モジュールとして追加）
4. **多言語custom_vocabulary**: Gladia APIのcustom_vocabularyパラメータに
   原稿から抽出した固有名詞を渡して文字起こし精度を上げる
5. **バッチ実行**: 複数案件を一括処理するスクリプト
6. **Google Colab版**: Colab上で動かせるnotebook版

---

## Claude Codeへの指示テンプレート

以下をClaude Codeに貼り付けて実行する:

```
このリポジトリに、TTS音声チェックツールを実装してください。
仕様書は tts-checker-spec.md を参照してください。

実装順序:
1. config.py
2. manuscript_parser.py + テスト
3. diff_engine.py + テスト
4. transcribe.py（Gladia API V2 pre-recorded）
5. report_generator.py（Jinja2テンプレートでHTML生成）
6. main.py（CLI統合）
7. README.md

注意点:
- Python 3.10+
- asyncioベースの並列文字起こし
- 文字起こしAPIは差し替え可能な設計にする（将来Whisper等に切替）
- HTMLレポートは単一ファイルで完結（CSS/JSインライン）
- テストは manuscript_parser と diff_engine に対して書く
```
