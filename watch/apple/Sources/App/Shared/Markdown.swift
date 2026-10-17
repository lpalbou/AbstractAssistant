import AbstractGatewayClient
import Foundation
import SwiftUI

/// Markdown for a 46 mm screen: the block structure an agent's answer actually uses (headings,
/// bullet and numbered lists, quotes, fenced code, tables, rules, paragraphs), each block's inline
/// marks (bold, italic, code, links) through Foundation's inline parser. Links are tappable: watchOS
/// opens web links in its own web view. Bare URLs become links too.
struct MarkdownText: View {
    let blocks: [MarkdownBlock]
    var font: Font = .rounded(.footnote)

    init(_ markdown: String, font: Font = .rounded(.footnote)) {
        self.blocks = MarkdownBlock.parse(markdown)
        self.font = font
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in view(block) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func view(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            Text(Self.inline(text))
                .font(.rounded(level <= 1 ? .headline : level == 2 ? .subheadline : .footnote, weight: .bold))
                .foregroundStyle(Theme.text).padding(.top, level <= 2 ? 3 : 1)
        case .paragraph(let text):
            Text(Self.inline(text)).font(font).foregroundStyle(Theme.text)
        case .item(let marker, let depth, let text):
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(marker).font(font.monospacedDigit()).foregroundStyle(Theme.cyan)
                Text(Self.inline(text)).font(font).foregroundStyle(Theme.text)
            }
            .padding(.leading, CGFloat(depth) * 9)
        case .quote(let text):
            HStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 1).fill(Theme.indigo.opacity(0.7)).frame(width: 2)
                Text(Self.inline(text)).font(font.italic()).foregroundStyle(Theme.text2)
            }
        case .code(let text):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(text).font(.mono(.caption2)).foregroundStyle(Theme.text2).fixedSize()
            }
            .padding(6)
            .background(Theme.ground, in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Theme.line, lineWidth: 1))
        case .table(let rows):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                    Text(Self.inline(row.joined(separator: " · ")))
                        .font(i == 0 ? .rounded(.caption2, weight: .semibold) : .rounded(.caption2))
                        .foregroundStyle(i == 0 ? Theme.text : Theme.text2)
                    if i == 0 { Rectangle().fill(Theme.line).frame(height: 1) }
                }
            }
        case .rule:
            Rectangle().fill(Theme.line).frame(height: 1).padding(.vertical, 2)
        }
    }

    /// Inline marks with links styled and bare URLs linked. Falls back to the raw text when the
    /// inline parser refuses it (it never throws on ordinary prose).
    nonisolated static func inline(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace,
                                                              failurePolicy: .returnPartiallyParsedIfPossible)
        var out = (try? AttributedString(markdown: markdownAutolink(text), options: options)) ?? AttributedString(text)
        for run in out.runs where run.link != nil {
            out[run.range].foregroundColor = Theme.cyan
            out[run.range].underlineStyle = .single
        }
        for run in out.runs where run.inlinePresentationIntent?.contains(.code) == true {
            out[run.range].font = .mono(.caption)
            out[run.range].foregroundColor = Theme.cyan
        }
        return out
    }
}

