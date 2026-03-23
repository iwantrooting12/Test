"""TTS音声チェックツール — Flask Webアプリ。"""

import json
import os
import queue
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from diff_engine import compute_diff, match_ratio, normalize
from main import collect_audio_files, match_audio_to_entries
from manuscript_parser import parse_manuscript
from report_generator import generate_report_html
from transcribe import transcribe_files

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB

JOBS: dict[str, dict] = {}


def _sse_event(data: dict) -> str:
    """SSEイベント文字列を生成する。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    manuscript = request.files.get("manuscript")
    audio_files = request.files.getlist("audio_files")

    if not manuscript or not audio_files:
        return jsonify({"error": "原稿ファイルと音声ファイルを選択してください。"}), 400

    job_id = uuid.uuid4().hex
    job_dir = Path(tempfile.gettempdir()) / f"tts-checker-{job_id}"
    job_dir.mkdir(parents=True)

    ms_path = job_dir / manuscript.filename
    manuscript.save(ms_path)

    audio_dir = job_dir / "audio"
    audio_dir.mkdir()
    for f in audio_files:
        f.save(audio_dir / f.filename)

    api_key = request.form.get("api_key", "") or os.environ.get("GLADIA_API_KEY", "")
    lang = request.form.get("lang", "ja")

    JOBS[job_id] = {
        "job_dir": job_dir,
        "ms_path": ms_path,
        "audio_dir": audio_dir,
        "api_key": api_key,
        "lang": lang,
    }

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "ジョブが見つかりません。"}), 404

    def generate():
        progress_queue = queue.Queue()
        error_holder = {}
        result_holder = {}

        try:
            # 1. 原稿解析
            yield _sse_event({"stage": "parsing", "message": "原稿を解析中..."})

            entries = parse_manuscript(str(job["ms_path"]))

            # 2. 音声ファイル収集 & マッチング
            audio_files = collect_audio_files(job["audio_dir"])
            pairs = match_audio_to_entries(audio_files, entries)

            yield _sse_event({"stage": "matched", "total": len(pairs)})

            # 3. 文字起こし（別スレッドで実行し、進捗をキューで受信）
            def on_progress(done, total, filename):
                progress_queue.put({"stage": "transcribing", "done": done, "total": total, "filename": filename})

            def run_transcription():
                try:
                    result_holder["transcripts"] = transcribe_files(
                        [p["audio"] for p in pairs],
                        api_key=job["api_key"],
                        lang=job["lang"],
                        progress_callback=on_progress,
                    )
                except Exception as e:
                    error_holder["error"] = str(e)
                finally:
                    progress_queue.put(None)  # 終了シグナル

            thread = threading.Thread(target=run_transcription)
            thread.start()

            last_heartbeat = time.monotonic()
            while True:
                try:
                    msg = progress_queue.get(timeout=15)
                except queue.Empty:
                    # Heartbeat（Renderタイムアウト対策）
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.monotonic()
                    continue

                if msg is None:
                    break
                yield _sse_event(msg)

            thread.join()

            if "error" in error_holder:
                yield _sse_event({"stage": "error", "message": error_holder["error"]})
                return

            transcripts = result_holder["transcripts"]

            # 4. diff比較
            results = []
            for pair, transcript in zip(pairs, transcripts):
                m_text = normalize(pair["entry"]["text"])
                t_text = normalize(transcript["transcript"], strip_chars=[])
                diff = compute_diff(m_text, t_text)
                ratio = match_ratio(m_text, t_text)
                results.append({
                    "filename": pair["audio"].name,
                    "entry_id": pair["entry"]["id"],
                    "diff": diff,
                    "ratio": ratio,
                })

            # 5. レポート生成
            report_html = generate_report_html(results, str(job["ms_path"]))

            yield _sse_event({"stage": "done", "report_html": report_html})

        except Exception as e:
            yield _sse_event({"stage": "error", "message": str(e)})

        finally:
            # tmpファイル削除
            shutil.rmtree(job["job_dir"], ignore_errors=True)
            JOBS.pop(job_id, None)

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
