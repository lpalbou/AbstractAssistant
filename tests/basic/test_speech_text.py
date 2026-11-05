"""Speech text cleanup: markdown replies must be spoken as plain prose."""

from __future__ import annotations

import pytest

from abstractassistant.core.speech_text import speech_plain_text


@pytest.mark.basic
def test_speech_text_strips_markdown_headers_emphasis_and_emoji() -> None:
    md = "### \U0001f30d Geopolitics & Conflict\n\n- **US-Iran War Pause** \u2014 The US has paused strikes."
    out = speech_plain_text(md)
    assert "#" not in out
    assert "*" not in out
    assert "\U0001f30d" not in out
    # Heading becomes its own short sentence so streaming synthesis can split
    # early instead of fusing the heading into the first paragraph.
    assert "Geopolitics & Conflict." in out
    assert "US-Iran War Pause \u2014 The US has paused strikes." in out


@pytest.mark.basic
def test_speech_text_replaces_links_images_and_urls() -> None:
    md = "See [the report](https://example.com/x) and ![chart](https://example.com/c.png) or https://example.com/raw"
    out = speech_plain_text(md)
    assert "https://" not in out
    assert "the report" in out
    assert "chart" in out
    assert "link" in out


@pytest.mark.basic
def test_speech_text_omits_code_blocks_and_unwraps_inline_code() -> None:
    md = "Run `ls -la` first.\n\n```python\nprint('hello')\n```\n\nDone."
    out = speech_plain_text(md)
    assert "`" not in out
    assert "ls -la" in out
    assert "print(" not in out
    assert "Code block omitted." in out
    assert "Done." in out


@pytest.mark.basic
def test_speech_text_tables_and_rules_become_prose() -> None:
    md = "| Name | Role |\n| --- | --- |\n| Ada | Engineer |\n\n---\n\nEnd."
    out = speech_plain_text(md)
    assert "|" not in out
    assert "---" not in out
    assert "Name, Role." in out
    assert "Ada, Engineer." in out


@pytest.mark.basic
def test_speech_text_preserves_accented_prose_untouched() -> None:
    md = "Voici le r\u00e9sum\u00e9 des actualit\u00e9s d'aujourd'hui, tr\u00e8s d\u00e9taill\u00e9."
    assert speech_plain_text(md) == md


@pytest.mark.basic
def test_speech_text_keeps_existing_terminal_punctuation() -> None:
    md = "## Already ended!\n- item one:\n- item two"
    out = speech_plain_text(md)
    assert "Already ended!" in out
    assert "Already ended!." not in out
    assert "item one:" in out
    assert "item one:." not in out
    assert "item two." in out


@pytest.mark.basic
def test_speech_text_empty_and_whitespace() -> None:
    assert speech_plain_text("") == ""
    assert speech_plain_text("   \n  ") == ""


@pytest.mark.basic
def test_speech_text_pronounces_paths_and_comparisons_without_changing_names():
    text = "Folders in /Users/albou/ that are ≥ 2 GB. Try ~/Library, ~/Documents or ~/Downloads."
    assert speech_plain_text(text) == (
        "Folders in slash Users slash albou slash that are greater than or equal to 2 GB. "
        "Try home slash Library, home slash Documents or home slash Downloads."
    )
    assert speech_plain_text("Use `/tmp/report.txt`, `./notes` or `../cache`. x≤3 and y≠4.") == (
        "Use slash tmp slash report.txt, current directory slash notes or parent directory slash cache. "
        "x less than or equal to 3 and y not equal to 4."
    )


@pytest.mark.basic
def test_speech_path_conversion_preserves_fractions_dates_and_prose():
    text = "Use 1/2 or 1 /2 of it on 2026/11/05 or 2026 /11 /05 and/or tomorrow. Voici le résumé."
    assert speech_plain_text(text) == text
    assert speech_plain_text("See https://example.com/path then /tmp/results.") == "See link then slash tmp slash results."


@pytest.mark.basic
def test_speech_paths_keep_dot_directory_components():
    assert speech_plain_text("Use /tmp/. or ../../cache.") == (
        "Use slash tmp slash current directory or parent directory slash parent directory slash cache."
    )
