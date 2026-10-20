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
    /// A run of the conversation: the conversation's folder is read through it.
    private var anyRun: String? { model.anyRun(of: sessionId) }

    var body: some View {
        FitScroll {
            VStack(alignment: .leading, spacing: 6) {
                Text(session.flatMap { model.title(of: $0) } ?? "This conversation")
                    .font(.rounded(.headline)).foregroundStyle(Theme.text).lineLimit(3)
                    .accessibilityIdentifier("conversation.title")
                stats
                if let s = session {
                    NavigationLink(value: Route.session(s)) {
                        HStack(spacing: 6) {
                            Image(systemName: "list.bullet").font(.rounded(.caption2)).foregroundStyle(Theme.cyan).frame(width: 16)
                            Text("Every exchange").font(.rounded(.footnote, weight: .medium)).foregroundStyle(Theme.text)
                            Spacer(minLength: 2)
                            Image(systemName: "chevron.right").font(.system(size: 10, weight: .bold)).foregroundStyle(Theme.muted)
                        }
                        .padding(.vertical, 8).padding(.horizontal, 10)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.tap)
                    .accessibilityIdentifier("conversation.exchanges")
                }
                Text("Files").font(.rounded(.footnote, weight: .semibold)).foregroundStyle(Theme.text2).padding(.top, 4)
                if let files {
                    if files.files.isEmpty {
                        Text("No files yet").font(.rounded(.footnote)).foregroundStyle(Theme.muted)
                    }
                    ForEach(Array(files.files.enumerated()), id: \.element.id) { i, file in
                        FileCard(file: file) { model.path.append(.filePreview(files.files, i)) }
                    }
                    if files.folderTruncated {
                        Text("More files are in its folder on your gateway.").font(.rounded(.caption2)).foregroundStyle(Theme.muted)
                    }
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
        .task(id: "\(sessionId) \(anyRun ?? "")") { await load() }
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
                } else if model.hasMessages(sessionId) {
                    LoadingText(text: "Loading").font(.rounded(.footnote)).foregroundStyle(Theme.muted)   // not listed yet
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
        do { files = try await model.client.sessionFiles(sessionId: sessionId, folderRunId: anyRun); failed = false }
        catch is CancellationError { return }                  // a newer load replaces it
        catch let e as URLError where e.code == .cancelled { return }
        catch { failed = files == nil }
    }
}

/// One file: what it is, its size and when, and its share button on the right. A tap previews it,
/// the conversation's other files a swipe up or down away.
struct FileCard: View {
    let file: SessionFile
    let open: () -> Void
    @EnvironmentObject private var model: AppModel

    var body: some View {
        HStack(spacing: 6) {
            Button(action: open) {
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
            .accessibilityIdentifier("file.open")
            if file.fitsTheWatch {
                ShareLink(item: SharedFile(file: file, client: model.client), preview: SharePreview(file.fileName)) {
                    GlassIcon(symbol: "square.and.arrow.up", size: 30)
                }
                .buttonStyle(GlassPress())
                .accessibilityLabel("Share \(file.fileName)")
                .accessibilityIdentifier("file.share")
            }
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
        case nil: file.contentType.hasPrefix("image/") ? "Image" : file.contentType.contains("pdf") ? "PDF" : "File"
        }
    }

    private var symbol: String {
        switch file.media?.kind {
        case .image: "photo"
        case .audio: "waveform"
        case .video: "play.rectangle"
        case nil: file.contentType.hasPrefix("image/") ? "photo" : file.contentType.contains("pdf") ? "doc.richtext" : "doc"
        }
    }

    private var detail: String {
        var parts: [String] = [file.origin == .made ? "Made" : "Attached"]
        if let size = file.sizeBytes { parts.append(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file)) }
        if let at = file.createdAt { parts.append(SessionRow.ago(at)) }
        if !file.fitsTheWatch { parts.append("too large for the watch") }
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
