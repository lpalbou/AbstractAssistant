import Foundation

/// The readable part of an HTML page: its title and its headings, paragraphs and list items, in order.
/// A tag-level reading (scripts, styles and page chrome dropped; entities decoded), capped for a watch.
public struct WebPageText: Sendable {
    public var title: String?
    public var paragraphs: [String]
    /// The page's lead image (the one it gives for link previews: `og:image`, else `twitter:image`),
    /// resolved against the page's address.
    public var image: URL?

    public var text: String { paragraphs.joined(separator: "\n\n") }
    public var markdown: String { text }

    public init(title: String?, paragraphs: [String]) { self.title = title; self.paragraphs = paragraphs }

    public init(html: String, base: URL? = nil) {
        var s = html
        func strip(_ pattern: String, _ with: String = " ") {
            guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive, .dotMatchesLineSeparators]) else { return }
            s = re.stringByReplacingMatches(in: s, range: NSRange(location: 0, length: (s as NSString).length), withTemplate: with)
        }
        func first(_ pattern: String) -> String? {
            guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive, .dotMatchesLineSeparators]),
                  let m = re.firstMatch(in: s, range: NSRange(location: 0, length: (s as NSString).length)), m.numberOfRanges > 1,
                  let r = Range(m.range(at: 1), in: s) else { return nil }
            return String(s[r])
        }
        let rawTitle = first(#"<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)"#) ?? first(#"<title[^>]*>(.*?)</title>"#)
        let rawImage = first(#"<meta[^>]+property=["']og:image(?::secure_url)?["'][^>]+content=["']([^"']+)"#)
            ?? first(#"<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']"#)
            ?? first(#"<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)"#)
        self.image = rawImage.flatMap { URL(string: Self.decode($0).trimmingCharacters(in: .whitespaces), relativeTo: base)?.absoluteURL }
            .flatMap { $0.scheme == "https" || $0.scheme == "http" ? $0 : nil }
        strip(#"<(script|style|noscript|svg|nav|header|footer|form|aside|template)\b.*?</\1>"#)
        strip(#"<!--.*?-->"#)
        strip(#"<h[1-3][^>]*>"#, "\n\n## ")
        strip(#"<li[^>]*>"#, "\n\n- ")
        strip(#"</?(p|div|section|article|br|tr|h[1-6]|ul|ol|table|blockquote)\b[^>]*>"#, "\n\n")
        strip(#"<[^>]+>"#, "")
        let decoded = Self.decode(s)
        var out: [String] = []
        var total = 0
        for block in decoded.components(separatedBy: "\n\n") {
            let line = block.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            let words = line.split(separator: " ").count
            let isHeading = line.hasPrefix("## ") && words >= 2
            guard isHeading || (line.hasPrefix("- ") ? words >= 4 : words >= 8) else { continue }
            if out.last == line { continue }
            out.append(line); total += line.count
            if total > 6000 { break }
        }
        while let last = out.last, last.hasPrefix("## ") { out.removeLast() }
        self.title = rawTitle.map { Self.decode($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        self.paragraphs = out
    }

    public static func decode(_ s: String) -> String {
        var out = s
        for (k, v) in ["&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": "\"", "&#39;": "'", "&apos;": "'",
                       "&mdash;": "—", "&ndash;": "–", "&hellip;": "…", "&rsquo;": "’", "&lsquo;": "‘", "&ldquo;": "“", "&rdquo;": "”"] {
            out = out.replacingOccurrences(of: k, with: v)
        }
        guard let re = try? NSRegularExpression(pattern: #"&#(x?)([0-9a-fA-F]+);"#) else { return out }
        let ns = out as NSString
        var result = ""; var last = 0
        for m in re.matches(in: out, range: NSRange(location: 0, length: ns.length)) {
            result += ns.substring(with: NSRange(location: last, length: m.range.location - last))
            let hex = ns.substring(with: m.range(at: 1)) == "x"
            if let code = UInt32(ns.substring(with: m.range(at: 2)), radix: hex ? 16 : 10), let u = Unicode.Scalar(code) { result.unicodeScalars.append(u) }
            last = m.range.location + m.range.length
        }
        return result + ns.substring(from: last)
    }
}
