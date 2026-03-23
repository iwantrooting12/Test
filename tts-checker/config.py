# テキスト正規化時に原稿から除去する文字
STRIP_CHARS_FROM_MANUSCRIPT = ["，", "《", "》"]

# ステータス判定閾値
THRESHOLD_OK = 0.99       # 99%以上 → OK
THRESHOLD_WARNING = 0.95  # 95%以上 → 要確認、未満 → 要修正

# Gladia API
GLADIA_API_BASE = "https://api.gladia.io/v2"
GLADIA_POLL_INTERVAL = 3      # 秒
GLADIA_POLL_TIMEOUT = 300     # 秒
GLADIA_MAX_CONCURRENT = 2     # 並列数（レート制限対策で控えめに）
GLADIA_MAX_RETRIES = 5
GLADIA_REQUEST_DELAY = 3      # リクエスト間の待ち時間（秒）

# 音声ファイル拡張子
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
