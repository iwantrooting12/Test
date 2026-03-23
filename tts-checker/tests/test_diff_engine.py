"""diff_engine のテスト。"""

from diff_engine import compute_diff, match_ratio, normalize


class TestNormalize:
    def test_fullwidth_to_halfwidth(self):
        """全角英数字が半角に変換される。"""
        assert normalize("Ａ Ｂ Ｃ１２３", strip_chars=[]) == "A B C123"

    def test_halfwidth_kana_to_fullwidth(self):
        """半角カナが全角に変換される。"""
        result = normalize("ｱｲｳ", strip_chars=[])
        assert result == "アイウ"

    def test_strip_chars(self):
        """指定文字が除去される。"""
        text = "桂ゆき，作、《婦人の日》。"
        result = normalize(text, strip_chars=["，", "《", "》"])
        assert "，" not in result
        assert "《" not in result
        assert "》" not in result
        assert "桂ゆき" in result
        assert "婦人の日" in result

    def test_whitespace_collapse(self):
        """連続空白が単一スペースに。"""
        assert normalize("あ  い　　う\n\nえ", strip_chars=[]) == "あ い う え"

    def test_strip(self):
        """前後の空白が除去される。"""
        assert normalize("  テスト  ", strip_chars=[]) == "テスト"

    def test_default_strip_chars(self):
        """デフォルトの除去文字（config.py準拠）。"""
        text = "桂ゆき，作、《婦人の日》。"
        result = normalize(text)
        assert "，" not in result
        assert "《" not in result


class TestComputeDiff:
    def test_identical(self):
        """完全一致。"""
        diffs = compute_diff("あいう", "あいう")
        assert len(diffs) == 1
        assert diffs[0]["tag"] == "equal"

    def test_replace(self):
        """置換。"""
        diffs = compute_diff("溌剌", "溌溂")
        tags = [d["tag"] for d in diffs]
        assert "replace" in tags

    def test_delete(self):
        """原稿にあるが文字起こしにない（欠落）。"""
        diffs = compute_diff("あいうえ", "あいえ")
        tags = [d["tag"] for d in diffs]
        assert "delete" in tags

    def test_insert(self):
        """文字起こしに追加がある。"""
        diffs = compute_diff("あいえ", "あいうえ")
        tags = [d["tag"] for d in diffs]
        assert "insert" in tags

    def test_empty_strings(self):
        """空文字列同士。"""
        diffs = compute_diff("", "")
        assert diffs == []


class TestMatchRatio:
    def test_identical(self):
        assert match_ratio("テスト", "テスト") == 1.0

    def test_completely_different(self):
        ratio = match_ratio("あああ", "いいい")
        assert ratio == 0.0

    def test_partial_match(self):
        ratio = match_ratio("あいう", "あいえ")
        assert 0.0 < ratio < 1.0
