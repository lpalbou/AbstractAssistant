"""Gateway text in a tooltip reads as written, never rendered (review of 0.18.3)."""
from abstractassistant.app import plain_tooltip


def test_an_html_error_page_reads_as_text():
    page = "<html><h1>502 Bad Gateway</h1><img src='file:///etc/passwd'></html>"
    out = plain_tooltip(page)
    assert "<h1>" not in out and "<img" not in out
    assert "&lt;h1&gt;502 Bad Gateway&lt;/h1&gt;" in out


def test_plain_words_stay_whole():
    assert "The gateway is not reachable." in plain_tooltip("The gateway is not reachable.")
