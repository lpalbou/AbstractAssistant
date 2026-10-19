import AbstractGatewayClient
import CoreTransferable
import SwiftUI
import UniformTypeIdentifiers
import WatchKit

/// The conversation: what it has been (questions, tool calls, thinking steps, when it started and
/// last moved) and its files, each with its share button.
struct ConversationInfoView: View {
    let sessionId: String
    @EnvironmentObject private var model: AppModel
    @State private var files: SessionFiles?
    @State private var failed = false

    private var session: SessionSummary? { model.sessions.first { $0.id == sessionId } }

    var body: some View {
        FitScroll {
            VStack(alignment: .leading, spacing: 6) {
                Text(session.flatMap { model.title(of: $0) } ?? "This conversation")
                    .font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(3)
                    .accessibilityIdentifier("conversation.title")
                stats
                Text("Files").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).padding(.top, 4)
                if let files {
                    if files.files.isEmpty {
                        Text("No files yet").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    }
                    ForEach(files.files) { FileCard(file: $0) }
                } else if failed {
                    Button("Couldn't load the files. Retry") { Task { await load() } }
                        .buttonStyle(.tap).font(.rounded(.footnote)).foregroundStyle(Theme.amber)
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal, 4)
        }
        .besideBack { EmptyView() }
        .task(id: sessionId) { await load() }
    }

    private var stats: some View {
        Card {
            VStack(alignment: .leading, spacing: 3) {
                if let s = session {
                    stat("bubble.left.and.bubble.right", "\(s.turns) \(s.turns == 1 ? "question" : "questions")")
                    if s.toolCalls > 0 { stat("wrench.and.screwdriver", "\(s.toolCalls) tool \(s.toolCalls == 1 ? "call" : "calls")") }
                    if s.llmCalls > 0 { stat("sparkles", "\(s.llmCalls) thinking \(s.llmCalls == 1 ? "step" : "steps")") }
                    if let first = model.runs.last(where: { $0.sessionId == s.id })?.createdAt.flatMap(ISO8601.date) {
                        stat("calendar", "Started \(first.formatted(date: .abbreviated, time: .shortened))")
                    }
                    if let at = s.updatedAt { stat("clock", "Last activity \(SessionRow.ago(at))") }
                } else {
                    stat("bubble.left.and.bubble.right", "Not started yet")
                }
                if let files {
                    stat("doc", "\(files.files.count) \(files.files.count == 1 ? "file" : "files")")
                    if files.spokenQuestions > 0 { stat("mic", "\(files.spokenQuestions) spoken") }
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("conversation.stats")
    }

    private func stat(_ symbol: String, _ text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).font(.rounded(.caption2)).foregroundStyle(Theme.cyan).frame(width: 16)
            Text(text).font(.rounded(.footnote)).foregroundStyle(Theme.text).lineLimit(2)
        }
    }

    private func load() async {
        do { files = try await model.client.sessionFiles(sessionId: sessionId); failed = false }
        catch { failed = files == nil }
    }
}

/// One file: what it is, its size and when, and its share button on the right. An image, a
/// recording or a video opens on the watch.
struct FileCard: View {
    let file: SessionFile
    @EnvironmentObject private var model: AppModel

    var body: some View {
        HStack(spacing: 6) {
            Button { if let m = file.media { model.path.append(.media(m)) } } label: {
                HStack(spacing: 6) {
                    Image(systemName: symbol).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.cyan).frame(width: 22)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(file.name ?? kind).font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                        Text(detail).font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                    }
                    Spacer(minLength: 2)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.tap)
            .disabled(file.media == nil)
            ShareLink(item: SharedFile(file: file, client: model.client), preview: SharePreview(file.fileName)) {
                GlassIcon(symbol: "square.and.arrow.up", size: 30)
            }
            .buttonStyle(GlassPress())
            .accessibilityLabel("Share \(file.fileName)")
            .accessibilityIdentifier("file.share")
        }
        .padding(.vertical, 6).padding(.horizontal, 8)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("file.card")
    }

    private var kind: String {
        switch file.media?.kind {
        case .image: "Image"
        case .audio: "Recording"
        case .video: "Video"
        case nil: file.contentType.contains("pdf") ? "PDF" : "File"
        }
    }

    private var symbol: String {
        switch file.media?.kind {
        case .image: "photo"
        case .audio: "waveform"
        case .video: "play.rectangle"
        case nil: file.contentType.contains("pdf") ? "doc.richtext" : "doc"
        }
    }

    private var detail: String {
        var parts: [String] = [file.origin == .made ? "Made" : "Attached"]
        if let size = file.sizeBytes { parts.append(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file)) }
        if let at = file.createdAt { parts.append(SessionRow.ago(at)) }
        return parts.joined(separator: " · ")
    }
}

/// A file to share: downloaded only when it is shared (the list costs nothing).
struct SharedFile: Transferable {
    let file: SessionFile
    let client: any GatewayClient

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .data) { shared in
            let data = try await shared.client.fileData(shared.file)
            let url = FileManager.default.temporaryDirectory.appending(path: shared.file.fileName)
            try data.write(to: url, options: .atomic)
            return SentTransferredFile(url)
        }
    }
}
