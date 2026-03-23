# TTS音声チェックツール

Azure TTSで生成した多言語AI音声の品質チェックツール。
音声ファイルをGladia APIで文字起こしし、原稿テキストと文字単位で比較して、
固有名詞の誤読・単語の欠落・追加などのクリティカルな誤りを検出する。

## セットアップ

```bash
cd tts-checker
pip install -r requirements.txt
```

## 使い方

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
| `--lang` | △ | 音声の言語コード（デフォルト: `ja`） |
| `--gladia-key` | △ | Gladia APIキー。未指定なら環境変数 `GLADIA_API_KEY` を参照 |
| `--no-normalize` | △ | テキスト正規化をスキップ |

## 環境変数

```bash
export GLADIA_API_KEY="your-api-key-here"
```

## 設定

`config.py` で以下をカスタマイズ可能:

- `STRIP_CHARS_FROM_MANUSCRIPT`: 正規化時に原稿から除去する文字
- `THRESHOLD_OK` / `THRESHOLD_WARNING`: ステータス判定閾値
- `GLADIA_MAX_CONCURRENT`: 並列文字起こし数
