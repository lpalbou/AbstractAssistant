import XCTest
import SwiftUI
@testable import AbstractAssistantPhone

/// An automation's cards show the answer's Markdown rendered, never its markers, in the room the
/// plain text had (operator 2026-11-03: a run card read `**Monday, November second…**`).
final class AutomationPreviewTests: XCTestCase {
    private let answer = """
    # Morning digest

    **Monday, November second.** Three things today: the assay QC run *passed*; two new papers on \
    your target ([one with a readout](https://example.org/paper)); the dependency check found one update.

    - Pin `numpy` before Friday.
    - Read the phase II summary.
    """

    @MainActor func testThePreviewShowsNoMarkdownMarkers() {
        let text = String(AutomationMarkdownPreview.formatted(answer, font: .subheadline, headingFont: .subheadline.weight(.semibold)).characters)
        for marker in ["**", "# ", "](", "`", "*passed*"] { XCTAssertFalse(text.contains(marker), "\(marker) left in: \(text)") }
        XCTAssertTrue(text.hasPrefix("Morning digest\nMonday, November second. Three things today"), text)
        XCTAssertTrue(text.contains("one with a readout"))
    }

    @MainActor func testBoldAndHeadingsAreStyledNotSpelledOut() {
        let formatted = AutomationMarkdownPreview.formatted(answer, font: .subheadline, headingFont: .subheadline.weight(.semibold))
        let bold = formatted.runs.contains { run in
            String(formatted[run.range].characters).contains("Monday") && run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true
        }
        XCTAssertTrue(bold, "the bold words lost their emphasis")
    }

    /// A run card's preview keeps today's size: three lines of subheadline, as the plain text was.
    @MainActor func testARunCardPreviewKeepsThePlainTextHeight() {
        let width: CGFloat = 358
        func height(_ view: some View) -> CGFloat {
            UIHostingController(rootView: view.frame(width: width)).sizeThatFits(in: CGSize(width: width, height: 2000)).height
        }
        let preview = height(AutomationMarkdownPreview(text: answer, lines: 3, font: .subheadline, headingFont: .subheadline.weight(.semibold), color: .primary, spacing: 0))
        let plain = height(Text(answer).font(.subheadline).lineLimit(3).fixedSize(horizontal: false, vertical: true))
        // A bold heading line adds a point or two; a line more (about 19 pt) would be a regression.
        XCTAssertEqual(preview, plain, accuracy: 4, "the rendered preview is \(preview) pt tall, the plain text was \(plain) pt")
        let short = height(AutomationMarkdownPreview(text: "**Done.**", lines: 3, font: .subheadline, color: .primary, spacing: 0))
        XCTAssertLessThan(short, plain / 2, "a one-line answer should take one line")
    }
}
