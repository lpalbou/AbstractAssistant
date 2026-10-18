import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func markdownBlocksCoverWhatAgentsWrite() {
    let md = """
    ## Survival by arm
    Overall survival **favoured arm B**:
    HR 0.78.

    - n = 412
      - nested
    1. first
    - [x] done

    | Arm | OS |
    |---|---|
    | A | 14.2 |

    > not adjusted

    ```python
    print("x")
    ```
    ---
    """
    let blocks = MarkdownBlock.parse(md)
    #expect(blocks == [
        .heading(2, "Survival by arm"),
        .paragraph("Overall survival **favoured arm B**: HR 0.78."),
        .item(marker: "•", depth: 0, "n = 412"),
        .item(marker: "•", depth: 1, "nested"),
        .item(marker: "1.", depth: 0, "first"),
        .item(marker: "☑", depth: 0, "done"),
        .table([["Arm", "OS"], ["A", "14.2"]]),
        .quote("not adjusted"),
        .code("print(\"x\")"),
        .rule,
    ])
}

@Test func speechTextReadsProseNotMarkup() {
    let spoken = SpeechText.plain("""
    ## Result
    The **deepest** point is [Challenger Deep](https://x.org), see https://en.wikipedia.org/wiki/X
    - over 1,000 atmospheres
    ```
    rm -rf /
    ```
    """)
    #expect(spoken == "Result. The deepest point is Challenger Deep, see. Over 1,000 atmospheres. A code block is shown on screen."
            || spoken == "Result. The deepest point is Challenger Deep, see. over 1,000 atmospheres. A code block is shown on screen.")
    #expect(!spoken.contains("**") && !spoken.contains("http") && !spoken.contains("rm -rf"))
}

@Test func bareURLsBecomeLinksButMarkdownLinksAreLeftAlone() {
    #expect(markdownAutolink("see https://a.org/x.") == "see <https://a.org/x>.")
    #expect(markdownAutolink("[a](https://a.org)") == "[a](https://a.org)")
}

@Test func webPageTextKeepsTheReadablePart() {
    let html = """
    <html><head><title>Mariana Trench &amp; more</title><style>p{}</style><script>var x = "<p>no</p>";</script></head>
    <body><nav><a>Home</a> <a>About us and everything else here</a></nav>
    <h1>The deepest place</h1><p>The Mariana Trench is the deepest oceanic trench on Earth, east of the Mariana Islands.</p>
    <ul><li>Depth of about eleven kilometres below the surface</li><li>short</li></ul>
    <footer>Copyright notice that is long enough to be counted as a paragraph</footer></body></html>
    """
    let page = WebPageText(html: html)
    #expect(page.title == "Mariana Trench & more")
    #expect(page.paragraphs == ["## The deepest place",
                                "The Mariana Trench is the deepest oceanic trench on Earth, east of the Mariana Islands.",
                                "- Depth of about eleven kilometres below the surface"])
    #expect(WebPageText.decode("caf&#233; &#x2014; ok") == "café — ok")
}

@Test func speechStreamEventsAndMockAudioDecode() throws {
    let line = #"{"type":"audio","sequence":0,"audio_b64":"UklGRg==","content_type":"audio/wav"}"#
    let ev = try JSONDecoder().decode(SpeechEvent.self, from: Data(line.utf8))
    #expect(ev.type == "audio" && Data(base64Encoded: ev.audioB64 ?? "") == Data("RIFF".utf8))
    let err = try JSONDecoder().decode(SpeechEvent.self, from: Data(#"{"type":"error","error":"audio/speech failed (404)"}"#.utf8))
    #expect(err.error == "audio/speech failed (404)")
    let wav = SyntheticSpeech.wav(seconds: 0.5, seed: 1)
    #expect(wav.prefix(4) == Data("RIFF".utf8) && wav.count == 44 + 16_000)
}

@Test func readAloudSpeaksTheWholeTextAsSentences() {
    // One request for the whole text: headings and list items become sentences of their own, so the
    // gateway's voice splits it at sentence ends.
    let md = "## Title\nFirst paragraph is here.\n\n- item one\n- item two\n\nA closing paragraph."
    #expect(SpeechText.plain(md) == "Title. First paragraph is here. item one. item two. A closing paragraph.")
}
