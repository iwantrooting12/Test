"""HTMLレポート生成モジュール。"""

from datetime import datetime
from pathlib import Path

from jinja2 import Template

from config import THRESHOLD_OK, THRESHOLD_WARNING

HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TTS音声チェックレポート</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Hiragino Sans', 'Meiryo', sans-serif; background: #f5f5f5; color: #333; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 1.5em; margin-bottom: 10px; }
.meta { color: #666; margin-bottom: 20px; font-size: 0.9em; }
.meta span { margin-right: 20px; }
.status-ok { color: #27ae60; font-weight: bold; }
.status-warning { color: #f39c12; font-weight: bold; }
.status-error { color: #e74c3c; font-weight: bold; }
.detail { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.detail h2 { font-size: 1.1em; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #eee; }
.detail-section { margin-bottom: 15px; }
.detail-section h3 { font-size: 0.9em; color: #666; margin-bottom: 5px; }
.text-display { background: #fafafa; padding: 12px; border-radius: 4px; line-height: 1.8; font-size: 0.95em; word-break: break-all; }
.diff-replace { background-color: #ffcccc; font-weight: bold; }
.diff-delete { background-color: #fff3cd; text-decoration: line-through; }
.diff-insert { background-color: #cce5ff; font-weight: bold; }
.diff-list { margin-top: 10px; }
.diff-list details { margin-bottom: 5px; }
.diff-list summary { cursor: pointer; color: #2c3e50; font-weight: bold; }
.diff-item { padding: 5px 10px; font-size: 0.9em; border-left: 3px solid #e74c3c; margin: 5px 0; background: #fff5f5; }
.overall-ratio { font-size: 1.2em; font-weight: bold; }
</style>
</head>
<body>
<div class="container">
<h1>TTS音声チェックレポート</h1>
<div class="meta">
  <span>生成日時: {{ generated_at }}</span>
  <span>原稿: {{ manuscript_name }}</span>
  <span>音声ファイル数: {{ results | length }}</span>
  <span class="overall-ratio">全体一致率: {{ "%.1f" | format(overall_ratio * 100) }}%</span>
</div>

{% for r in results %}
<div class="detail" id="detail-{{ loop.index }}">
  <h2>#{{ r.entry_id }} — {{ r.filename }} （一致率: {{ "%.1f" | format(r.ratio * 100) }}%）</h2>

  <div class="detail-section">
    <h3>[文字起こし]</h3>
    <div class="text-display">{{ r.transcript_html }}</div>
  </div>

  <div class="detail-section">
    <h3>[原稿]</h3>
    <div class="text-display">{{ r.manuscript_html }}</div>
  </div>

  {% if r.diff_items %}
  <div class="diff-list">
    <details>
      <summary>差分一覧 ({{ r.diff_items | length }}件)</summary>
      {% for item in r.diff_items %}
      <div class="diff-item">{{ item }}</div>
      {% endfor %}
    </details>
  </div>
  {% endif %}
</div>
{% endfor %}

</div>
</body>
</html>
""")


def _get_status(ratio: float) -> tuple[str, str]:
    """一致率からステータスラベルとCSSクラスを返す。"""
    if ratio >= THRESHOLD_OK:
        return "✓ OK", "status-ok"
    elif ratio >= THRESHOLD_WARNING:
        return "⚠ 要確認", "status-warning"
    else:
        return "✗ 要修正", "status-error"


def _build_highlighted_html(diff: list[dict], side: str) -> str:
    """diff結果からハイライト付きHTMLを生成する。"""
    parts = []
    key = "manuscript_slice" if side == "manuscript" else "transcript_slice"
    for d in diff:
        text = d[key]
        if not text:
            continue
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        tag = d["tag"]
        if tag == "equal":
            parts.append(escaped)
        elif tag == "replace":
            parts.append(f'<span class="diff-replace">{escaped}</span>')
        elif tag == "delete":
            if side == "manuscript":
                parts.append(f'<span class="diff-delete">{escaped}</span>')
        elif tag == "insert":
            if side == "transcript":
                parts.append(f'<span class="diff-insert">{escaped}</span>')
    return "".join(parts)


def _build_diff_items(diff: list[dict]) -> list[str]:
    """差分一覧テキストを生成する。"""
    items = []
    pos = 0
    for d in diff:
        tag = d["tag"]
        ms = d["manuscript_slice"]
        ts = d["transcript_slice"]
        if tag == "replace":
            items.append(f"位置 {pos}: 原稿「{ms}」→ 文字起こし「{ts}」")
        elif tag == "delete":
            items.append(f"位置 {pos}: 欠落「{ms}」")
        elif tag == "insert":
            items.append(f"位置 {pos}: 追加「{ts}」")
        pos += len(ms) if ms else 0
    return items


def generate_report_html(results: list[dict], manuscript_name: str) -> str:
    """HTMLレポートを生成して文字列で返す。

    Args:
        results: main.pyから渡される結果リスト
        manuscript_name: 原稿ファイル名

    Returns:
        HTMLレポート文字列
    """
    template_data = []
    total_ratio = 0.0

    for r in results:
        status_label, status_class = _get_status(r["ratio"])
        template_data.append({
            "filename": r["filename"],
            "entry_id": r["entry_id"],
            "ratio": r["ratio"],
            "status_label": status_label,
            "status_class": status_class,
            "transcript_html": _build_highlighted_html(r["diff"], "transcript"),
            "manuscript_html": _build_highlighted_html(r["diff"], "manuscript"),
            "diff_items": _build_diff_items(r["diff"]),
        })
        total_ratio += r["ratio"]

    overall_ratio = total_ratio / len(results) if results else 0.0

    return HTML_TEMPLATE.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        manuscript_name=Path(manuscript_name).name,
        results=template_data,
        overall_ratio=overall_ratio,
    )


def generate_report(results: list[dict], output_path: str | Path, manuscript_name: str) -> None:
    """HTMLレポートを生成してファイルに書き出す。"""
    html = generate_report_html(results, manuscript_name)
    Path(output_path).write_text(html, encoding="utf-8")
