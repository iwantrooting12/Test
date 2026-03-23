"""manuscript_parser のテスト。"""

import tempfile
from pathlib import Path

from manuscript_parser import parse_manuscript


def test_numbered_txt():
    """番号付きtxtファイルのパース。"""
    content = "1\n桂ゆき，作、《婦人の日》。\n\n2\n佐藤忠良，作、《帽子・夏》。\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(content)
        f.flush()
        entries = parse_manuscript(f.name)

    assert len(entries) == 2
    assert entries[0]["id"] == "1"
    assert "桂ゆき" in entries[0]["text"]
    assert entries[1]["id"] == "2"
    assert "佐藤忠良" in entries[1]["text"]


def test_unnumbered_txt():
    """番号なしtxtファイルのパース（空行区切り）。"""
    content = "これは最初のエントリです。\n行が続きます。\n\nこれは2番目のエントリです。\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(content)
        f.flush()
        entries = parse_manuscript(f.name)

    assert len(entries) == 2
    assert entries[0]["id"] == "1"
    assert "最初" in entries[0]["text"]
    assert entries[1]["id"] == "2"
    assert "2番目" in entries[1]["text"]


def test_empty_txt():
    """空のtxtファイル。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write("")
        f.flush()
        entries = parse_manuscript(f.name)

    assert entries == []


def test_single_entry_txt():
    """1エントリだけのtxtファイル。"""
    content = "1\nこれは唯一のエントリです。\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(content)
        f.flush()
        entries = parse_manuscript(f.name)

    assert len(entries) == 1
    assert entries[0]["id"] == "1"
    assert "唯一" in entries[0]["text"]


def test_multiline_entry():
    """番号付きで複数行のテキストを含むエントリ。"""
    content = "1\n最初の行。\n2行目。\n3行目。\n\n2\n次のエントリ。\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(content)
        f.flush()
        entries = parse_manuscript(f.name)

    assert len(entries) == 2
    assert "3行目" in entries[0]["text"]


def test_xlsx_two_columns(tmp_path):
    """2列のxlsxファイル。"""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([1, "テスト文1"])
    ws.append([2, "テスト文2"])
    path = tmp_path / "test.xlsx"
    wb.save(str(path))

    entries = parse_manuscript(path)
    assert len(entries) == 2
    assert entries[0]["id"] == "1"
    assert entries[0]["text"] == "テスト文1"


def test_unsupported_format():
    """未対応の形式でValueError。"""
    import pytest

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        with pytest.raises(ValueError, match="未対応"):
            parse_manuscript(f.name)
