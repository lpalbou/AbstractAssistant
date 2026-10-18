import Foundation

public enum MarkdownBlock: Equatable, Sendable {
    case heading(Int, String)
    case paragraph(String)
    case item(marker: String, depth: Int, String)
    case quote(String)
    case code(String)
    case table([[String]])
    case rule

    public static func parse(_ markdown: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var paragraph: [String] = []
        var quote: [String] = []
        var table: [[String]] = []
        var code: [String]?

        func flush() {
            if !paragraph.isEmpty { blocks.append(.paragraph(paragraph.joined(separator: " "))); paragraph = [] }
            if !quote.isEmpty { blocks.append(.quote(quote.joined(separator: " "))); quote = [] }
            if !table.isEmpty { blocks.append(.table(table)); table = [] }
        }

        for raw in markdown.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("```") || line.hasPrefix("~~~") {
                if let open = code { blocks.append(.code(open.joined(separator: "\n"))); code = nil }
                else { flush(); code = [] }
                continue
            }
            if code != nil { code?.append(raw); continue }
            if line.isEmpty { flush(); continue }

            if let h = heading(line) { flush(); blocks.append(h); continue }
            if line.count >= 3, Set(line.replacingOccurrences(of: " ", with: "")).count == 1, "-*_".contains(line.first!) {
                flush(); blocks.append(.rule); continue
            }
            if line.hasPrefix("|") {
                if !paragraph.isEmpty || !quote.isEmpty { let t = table; table = []; flush(); table = t }
                let cells = line.trimmingCharacters(in: CharacterSet(charactersIn: "|")).components(separatedBy: "|")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                let isSeparator = cells.allSatisfy { !$0.isEmpty && $0.allSatisfy { "-:".contains($0) } }
                if !isSeparator { table.append(cells) }
                continue
            }
            if line.hasPrefix(">") {
                if !paragraph.isEmpty || !table.isEmpty { let q = quote; quote = []; flush(); quote = q }
                quote.append(String(line.dropFirst()).trimmingCharacters(in: .whitespaces)); continue
            }
            if let item = listItem(raw) { flush(); blocks.append(item); continue }
            if !quote.isEmpty || !table.isEmpty { flush() }
            paragraph.append(line)
        }
        if let open = code { blocks.append(.code(open.joined(separator: "\n"))) }
        flush()
        return blocks
    }

    private static func heading(_ line: String) -> MarkdownBlock? {
        let hashes = line.prefix { $0 == "#" }.count
        guard (1...6).contains(hashes), line.dropFirst(hashes).first == " " else { return nil }
        return .heading(hashes, line.dropFirst(hashes).trimmingCharacters(in: CharacterSet(charactersIn: " #")))
    }

    private static func listItem(_ raw: String) -> MarkdownBlock? {
        let indent = raw.prefix { $0 == " " || $0 == "\t" }.reduce(0) { $0 + ($1 == "\t" ? 4 : 1) }
        let line = raw.trimmingCharacters(in: .whitespaces)
        let depth = min(indent / 2, 3)
        for bullet in ["- ", "* ", "+ ", "• "] where line.hasPrefix(bullet) {
            var text = String(line.dropFirst(bullet.count))
            var marker = "•"
            if text.hasPrefix("[ ] ") { marker = "☐"; text.removeFirst(4) }
            else if text.lowercased().hasPrefix("[x] ") { marker = "☑"; text.removeFirst(4) }
            return .item(marker: marker, depth: depth, text)
        }
        let digits = line.prefix { $0.isNumber }
        if !digits.isEmpty, digits.count <= 3 {
            let rest = line.dropFirst(digits.count)
            if rest.hasPrefix(". ") || rest.hasPrefix(") ") {
                return .item(marker: "\(digits).", depth: depth, String(rest.dropFirst(2)))
            }
        }
        return nil
    }
}

/// Markdown → prose a voice can read: headings and list items become their own sentences, code
/// blocks are announced rather than spelled out, links read as their label, bare URLs are dropped.
public enum SpeechText {
    public static func plain(_ markdown: String) -> String { plain(blocks: MarkdownBlock.parse(markdown)) }

    static func plain(blocks: [MarkdownBlock]) -> String {
        var sentences: [String] = []
        for block in blocks {
            switch block {
            case .heading(_, let t), .paragraph(let t), .quote(let t): sentences.append(sentence(t))
            case .item(_, _, let t): sentences.append(sentence(t))
            case .code: sentences.append("A code block is shown on screen.")
            case .table(let rows): sentences.append(contentsOf: rows.dropFirst().map { sentence($0.joined(separator: ", ")) })
            case .rule: break
            }
        }
        return sentences.filter { !$0.isEmpty }.joined(separator: " ")
    }

    private static func sentence(_ text: String) -> String {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace,
                                                              failurePolicy: .returnPartiallyParsedIfPossible)
        var s = String(((try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)).characters)
        if let re = try? NSRegularExpression(pattern: #"https?://\S+"#) {
            s = re.stringByReplacingMatches(in: s, range: NSRange(location: 0, length: (s as NSString).length), withTemplate: "")
        }
        s = s.replacingOccurrences(of: "  ", with: " ").trimmingCharacters(in: .whitespaces)
        guard let last = s.last else { return "" }
        return ".!?:".contains(last) ? s : s + "."
    }
}

/// `https://x` → `<https://x>` unless it is already the target or label of a markdown link.
public func markdownAutolink(_ text: String) -> String {
    guard text.contains("http") else { return text }
    let pattern = #"(?<![\(<\[])\bhttps?://[^\s<>\)\]]+[^\s<>\)\]\.,;:!?'"]"#
    guard let re = try? NSRegularExpression(pattern: pattern) else { return text }
    let ns = text as NSString
    return re.stringByReplacingMatches(in: text, range: NSRange(location: 0, length: ns.length), withTemplate: "<$0>")
}
