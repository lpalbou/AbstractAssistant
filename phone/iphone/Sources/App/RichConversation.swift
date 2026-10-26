import UIKit
import ImageIO
import UniformTypeIdentifiers
import AssistantKit
import PhoneGatewayClient
import LinkPresentation

@MainActor struct RichConversation {
    let body: NSAttributedString
    let html: Data
    let rtfd: Data
    let plain: Data

    init(export: ConversationExport) throws {
        let text = NSMutableAttributedString(string: "")
        var html = "<!doctype html><html><head><meta charset=\"utf-8\"><title>Conversation</title><style>body{font:16px -apple-system,Arial,sans-serif;line-height:1.5;color:#202331;max-width:760px;margin:32px auto;padding:0 20px}section{margin:28px 0}h2{font-size:18px;color:#3e4c72}img{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#f2f3f6;padding:14px}blockquote{border-left:3px solid #aaa;padding-left:16px}table{border-collapse:collapse}td{padding:6px 12px;border:1px solid #ddd}.file,.scope{color:#626878;font-size:14px}</style></head><body><h1>Conversation</h1><p class=\"scope\">Messages loaded in the app, with attached and recorded generated files. Workspace files reflect their current saved version.</p>"
        func append(_ value: String, size: CGFloat = 16, weight: UIFont.Weight = .regular, code: Bool = false) {
            text.append(NSAttributedString(string: value, attributes: [.font: code ? UIFont.monospacedSystemFont(ofSize: size, weight: weight) : UIFont.systemFont(ofSize: size, weight: weight), .foregroundColor: UIColor.black]))
        }
        func inline(_ source: String, size: CGFloat = 16, weight: UIFont.Weight = .regular) -> String {
            let value = (try? AttributedString(markdown: source, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(source)
            var rendered = ""
            for run in value.runs {
                let part = String(value[run.range].characters), intent = run.inlinePresentationIntent ?? []
                var font = intent.contains(.code) ? UIFont.monospacedSystemFont(ofSize: size, weight: .regular) : UIFont.systemFont(ofSize: size, weight: intent.contains(.stronglyEmphasized) ? .bold : weight)
                if intent.contains(.emphasized), let descriptor = font.fontDescriptor.withSymbolicTraits(font.fontDescriptor.symbolicTraits.union(.traitItalic)) { font = UIFont(descriptor: descriptor, size: size) }
                var attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.black]
                var h = Self.escape(part)
                if intent.contains(.code) { h = "<code>" + h + "</code>" }
                if intent.contains(.stronglyEmphasized) { h = "<strong>" + h + "</strong>" }
                if intent.contains(.emphasized) { h = "<em>" + h + "</em>" }
                if intent.contains(.strikethrough) { attributes[.strikethroughStyle] = NSUnderlineStyle.single.rawValue; h = "<s>" + h + "</s>" }
                if let link = run.link, ["https", "http", "mailto"].contains(link.scheme?.lowercased() ?? ""), link.user == nil, link.password == nil {
                    attributes[.link] = link; h = "<a href=\"" + Self.escape(link.absoluteString) + "\">" + h + "</a>"
                }
                text.append(NSAttributedString(string: part, attributes: attributes)); rendered += h
            }
            return rendered
        }
        append("Conversation\n", size: 25, weight: .bold)
        append("Messages loaded in the app, with attached and recorded generated files. Workspace files reflect their current saved version.\n\n", size: 12)
        let byID = Dictionary(uniqueKeysWithValues: export.files.map { ($0.id, $0) })
        var imageCount = 0
        for turn in export.turns {
            append(turn.speaker + "\n", size: 18, weight: .semibold); html += "<section><h2>" + Self.escape(turn.speaker) + "</h2>"
            for block in MarkdownBlock.parse(turn.text) {
                switch block {
                case .heading(let level, let value):
                    html += "<h\(min(level + 2, 6))>" + inline(value, size: level < 3 ? 19 : 17, weight: .semibold) + "</h\(min(level + 2, 6))>"; append("\n\n")
                case .paragraph(let value): html += "<p>" + inline(value) + "</p>"; append("\n\n")
                case .item(let marker, let depth, let value):
                    append(String(repeating: "    ", count: depth) + marker + " ")
                    html += "<p style=\"margin-left:\(depth * 18)px\">" + Self.escape(marker) + " " + inline(value) + "</p>"; append("\n")
                case .quote(let value): append("❝ "); html += "<blockquote>" + inline(value) + "</blockquote>"; append("\n\n")
                case .code(let value): append(value + "\n\n", size: 14, code: true); html += "<pre><code>" + Self.escape(value) + "</code></pre>"
                case .table(let rows):
                    html += "<table>"
                    for row in rows { html += "<tr>"; for (index, cell) in row.enumerated() { if index > 0 { append("\t") }; html += "<td>" + inline(cell, size: 14) + "</td>" }; append("\n"); html += "</tr>" }
                    append("\n"); html += "</table>"
                case .rule: append("────────────\n\n"); html += "<hr>"
                }
            }
            for id in turn.fileIDs {
                guard let file = byID[id] else { continue }
                if imageCount < 12, let image = Self.thumbnail(file.url) {
                    imageCount += 1
                    let attachment = NSTextAttachment(); attachment.image = image
                    let width = min(image.size.width, 320), height = width * image.size.height / max(image.size.width, 1)
                    attachment.bounds = CGRect(x: 0, y: 0, width: width, height: height)
                    text.append(NSAttributedString(attachment: attachment)); append("\n")
                    if let data = image.jpegData(compressionQuality: 0.85) { html += "<p><img alt=\"" + Self.escape(file.name) + "\" src=\"data:image/jpeg;base64," + data.base64EncodedString() + "\"></p>" }
                }
                append("Attachment: " + file.name + "\n", size: 13)
                html += "<p class=\"file\">Attachment: " + Self.escape(file.name) + "</p>"
            }
            append("\n"); html += "</section>"
        }
        html += "</body></html>"
        body = NSAttributedString(attributedString: text)
        self.html = Data(html.utf8); plain = Data(body.string.replacingOccurrences(of: "\u{fffc}", with: "").utf8)
        rtfd = try body.data(from: NSRange(location: 0, length: body.length), documentAttributes: [.documentType: NSAttributedString.DocumentType.rtfd])
        try self.html.write(to: export.folder.appending(path: "Conversation.html"), options: .atomic)
    }
    private static func thumbnail(_ url: URL) -> UIImage? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1000, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
        return UIImage(cgImage: image)
    }
    private static func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;").replacingOccurrences(of: "'", with: "&#39;")
    }
    func configuration(export: ConversationExport) -> UIActivityItemsConfiguration {
        let transcript = NSItemProvider(); transcript.suggestedName = "Conversation"
        for (type, data) in [(UTType.flatRTFD.identifier, rtfd), (UTType.html.identifier, html), (UTType.utf8PlainText.identifier, plain)] {
            transcript.registerDataRepresentation(forTypeIdentifier: type, visibility: .all) { completion in completion(data, nil); return nil }
        }
        transcript.registerFileRepresentation(forTypeIdentifier: UTType.html.identifier, fileOptions: [], visibility: .all) { completion in
            completion(export.folder.appending(path: "Conversation.html"), false, nil); return nil
        }
        let providers = [transcript] + export.files.map { file -> NSItemProvider in
            let provider = NSItemProvider(); provider.suggestedName = file.name
            let type = UTType(mimeType: file.contentType) ?? UTType(filenameExtension: file.url.pathExtension) ?? .data
            provider.registerFileRepresentation(forTypeIdentifier: type.identifier, fileOptions: [], visibility: .all) { completion in completion(file.url, false, nil); return nil }
            return provider
        }
        let configuration = UIActivityItemsConfiguration(itemProviders: providers)
        configuration.metadataProvider = { key in
            if key == .messageBody { return self.body }
            if key == .title { return "Conversation" }
            return nil
        }
        configuration.perItemMetadataProvider = { index, key in
            guard index == 0 else { return nil }
            if key == .title { return "Conversation" }
            if key == .linkPresentationMetadata {
                let metadata = LPLinkMetadata(); metadata.title = "Conversation"
                if let icon = UIImage(systemName: "bubble.left.and.bubble.right")?.withTintColor(.systemTeal, renderingMode: .alwaysOriginal) { metadata.iconProvider = NSItemProvider(object: icon) }
                return metadata
            }
            return nil
        }
        return configuration
    }
}
