from scripts.run_validation import (
    ASCII_PROGRESS_CHARS,
    UNICODE_PROGRESS_CHARS,
    _format_progress_bar,
    _progress_chars,
)


class _EncodingStream:
    def __init__(self, encoding):
        self.encoding = encoding


def test_progress_chars_use_ascii_when_stream_cannot_encode_blocks():
    stream = _EncodingStream("cp1252")

    assert _progress_chars(stream) == ASCII_PROGRESS_CHARS


def test_progress_chars_use_unicode_when_stream_can_encode_blocks():
    stream = _EncodingStream("utf-8")

    assert _progress_chars(stream) == UNICODE_PROGRESS_CHARS


def test_progress_bar_is_ascii_safe_for_legacy_windows_console():
    stream = _EncodingStream("cp1252")

    rendered = _format_progress_bar(5, 10, bar_len=10, stream=stream)

    assert rendered == "\r  Progress: [#####-----] 5/10 (50%)"
    rendered.encode("cp1252")
