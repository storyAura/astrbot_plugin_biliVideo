"""URL/BV extraction unit tests."""

from __future__ import annotations

from bilivideo.parsing.url_extractor import (
    detect_platform,
    extract_bvid,
    extract_long_url,
    extract_short_url,
    extract_uid,
    extract_url,
    is_bilibili_domain,
    is_short_bili_url,
    parse_json_card,
)


class TestExtractBvid:
    def test_match_in_url(self) -> None:
        assert extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD") == "BV1xx411c7mD"

    def test_match_bare_bv(self) -> None:
        assert extract_bvid("BV1xx411c7mD") == "BV1xx411c7mD"

    def test_nothing_when_missing(self) -> None:
        assert extract_bvid("just text") is None

    def test_handles_empty(self) -> None:
        assert extract_bvid("") is None

    def test_picks_first(self) -> None:
        text = "BV1xx411c7mD 还有 BV1yy123abc4"
        assert extract_bvid(text) == "BV1xx411c7mD"


class TestExtractUid:
    def test_pure_uid(self) -> None:
        assert extract_uid("12345") == "12345"

    def test_space_link(self) -> None:
        assert extract_uid("https://space.bilibili.com/12345/video") == "12345"

    def test_invalid(self) -> None:
        assert extract_uid("hello") is None


class TestExtractLongUrl:
    def test_video_url(self) -> None:
        assert (
            extract_long_url("看看 https://www.bilibili.com/video/BV1xx411c7mD?abc=1")
            == "https://www.bilibili.com/video/BV1xx411c7mD?abc=1"
        )

    def test_no_url(self) -> None:
        assert extract_long_url("BV1xx411c7mD only") is None


class TestExtractShortUrl:
    def test_short_url(self) -> None:
        assert extract_short_url("分享 https://b23.tv/abc123") == "https://b23.tv/abc123"

    def test_strips_punct(self) -> None:
        assert extract_short_url('https://b23.tv/abc"') == "https://b23.tv/abc"

    def test_strips_chinese_punctuation_from_short_url(self) -> None:
        assert extract_short_url("https://b23.tv/abc，") == "https://b23.tv/abc"
        assert extract_short_url("<https://b23.tv/abc。>") == "https://b23.tv/abc"
        assert extract_short_url("https://b23.tv/abc）") == "https://b23.tv/abc"
        assert extract_short_url("https://b23.tv/abc!") == "https://b23.tv/abc"

    def test_supports_other_bili_short_domains(self) -> None:
        assert extract_short_url("https://bili2233.cn/abc，") == "https://bili2233.cn/abc"
        assert extract_short_url("https://bili22.cn/abc") == "https://bili22.cn/abc"
        assert is_short_bili_url("https://bili23.cn/abc")
        assert is_short_bili_url("https://bili33.cn/abc")


class TestExtractUrl:
    def test_extracts_generic_video_url(self) -> None:
        assert extract_url("看这个 https://youtu.be/abc123，") == "https://youtu.be/abc123"
        assert (
            extract_url("<https://www.douyin.com/video/123)>")
            == "https://www.douyin.com/video/123"
        )

    def test_no_url(self) -> None:
        assert extract_url("BV1xx411c7mD only") is None


class TestDetectPlatform:
    def test_bilibili(self) -> None:
        assert detect_platform("https://www.bilibili.com/video/BV1") == "bilibili"
        assert detect_platform("https://b23.tv/xxx") == "bilibili"
        assert detect_platform("https://bili2233.cn/xxx") == "bilibili"

    def test_youtube(self) -> None:
        assert detect_platform("https://youtu.be/xxx") == "youtube"
        assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"

    def test_douyin_and_tiktok(self) -> None:
        assert detect_platform("https://www.douyin.com/video/123") == "douyin"
        assert detect_platform("https://www.tiktok.com/@u/video/123") == "douyin"

    def test_rejects_platform_substring_deception(self) -> None:
        assert detect_platform("https://notyoutube.com/watch?v=abc") is None
        assert detect_platform("https://evil.com/?next=youtube.com") is None
        assert detect_platform("https://douyin.com.evil.com/video/123") is None

    def test_none(self) -> None:
        assert detect_platform("") is None
        assert detect_platform("https://example.com") is None


class TestIsBilibiliDomain:
    def test_main_domain(self) -> None:
        assert is_bilibili_domain("https://www.bilibili.com/video/BV1xx")
        assert is_bilibili_domain("https://m.bilibili.com/")
        assert is_bilibili_domain("https://b23.tv/abc")

    def test_other_domain(self) -> None:
        assert not is_bilibili_domain("https://github.com")
        assert not is_bilibili_domain("https://evilbilibili.com")

    def test_rejects_substring_deception(self) -> None:
        # The earlier auto-detect guard used `"bili" in url`, which all of
        # these would satisfy. The hostname check must reject them so a
        # crafted link can never aim follow_redirect at a non-Bilibili host.
        assert not is_bilibili_domain("http://evil.com/?x=bili")
        assert not is_bilibili_domain("http://169.254.169.254/bili")
        assert not is_bilibili_domain("http://bilibili.com.evil.com/")
        assert not is_bilibili_domain("http://bili.evil.com/")


class TestParseJsonCard:
    def test_qqdocurl(self) -> None:
        text = (
            '{"meta":{"detail_1":{'
            '"qqdocurl":"https://b23.tv/abc",'
            '"title":"test"}}}'
        )
        assert parse_json_card(text) == "https://b23.tv/abc"

    def test_invalid_json(self) -> None:
        assert parse_json_card("not json") is None

    def test_empty(self) -> None:
        assert parse_json_card("") is None

    def test_qqdocurl_regex_fallback(self) -> None:
        text = '..."qqdocurl":"https://www.bilibili.com/video/BV1xx411c7mD"...'
        assert (
            parse_json_card(text)
            == "https://www.bilibili.com/video/BV1xx411c7mD"
        )
