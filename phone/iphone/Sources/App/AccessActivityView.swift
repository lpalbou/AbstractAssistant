import SwiftUI
import AssistantKit

extension AccessKind {
    var title: String { switch self { case .filesRead: "Files read"; case .filesChanged: "Files changed"; case .searches: "Web searches"; case .pages: "Web pages fetched" } }
    var symbol: String { switch self { case .filesRead, .filesChanged: "doc.text"; case .searches: "magnifyingglass"; case .pages: "globe" } }
}
struct AccessActionIcon: View {
    let kind: AccessKind
    var body: some View {
        Image(systemName: kind.symbol).overlay(alignment: .bottomTrailing) {
            if kind == .filesRead || kind == .filesChanged {
                Image(systemName: kind == .filesRead ? "arrow.down.left" : "pencil")
                    .font(.system(size: 8, weight: .bold)).padding(1.5).background(PhoneTheme.ground, in: Circle()).offset(x: 4, y: 3)
            }
        }.frame(width: 22, height: 18)
    }
}
struct AccessActivityView: View {
    let runID: String
    let kind: AccessKind
    let browseFiles: () -> Void
    @Environment(AssistantStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    private var access: AccessActivity? { store.answerActivities[runID]?.activity.access }
    private var rows: [AccessEntry] {
        (access?.items(kind) ?? []).filter { query.isEmpty || $0.target.localizedCaseInsensitiveContains(query) }
    }
    var body: some View {
        NavigationStack {
            List {
                if store.answerActivities[runID]?.issues.isEmpty == false {
                    Text("Some activity could not be loaded. Showing confirmed actions available so far.").font(.footnote).foregroundStyle(PhoneTheme.amber).listRowBackground(PhoneTheme.surface)
                }
                Section {
                    ForEach(Array(rows.enumerated()), id: \.element.id) { index, entry in
                        NavigationLink { AccessDetail(entry: entry, close: { dismiss() }, browseFiles: browseFiles) } label: {
                            VStack(alignment: .leading, spacing: 7) {
                                Text(kind == .filesRead || kind == .filesChanged ? (entry.target as NSString).lastPathComponent : kind == .pages ? (URL(string: entry.target)?.host ?? entry.target) : entry.target).font(.subheadline.weight(.semibold)).lineLimit(2)
                                if kind != .searches { Text(entry.target).font(.caption).foregroundStyle(PhoneTheme.mint).lineLimit(2) }
                                HStack {
                                    Text(entry.events.last?.mode ?? "")
                                    if entry.operations > 1 { Text("· \(entry.operations) actions") }
                                    Spacer()
                                    if let date = entry.events.last?.timestamp { Text(date.formatted(date: .abbreviated, time: .shortened)) }
                                }.font(.caption2).foregroundStyle(PhoneTheme.secondary)
                            }.padding(.vertical, 8)
                        }.accessibilityIdentifier("access.row.\(index)").listRowBackground(PhoneTheme.surface)
                    }
                } footer: {
                    VStack(alignment: .leading, spacing: 6) {
                        if (access?.count(kind) ?? 0) > (access?.items(kind).count ?? 0) { Text("Showing the latest 100 sources.") }
                        Text(kind == .filesRead || kind == .filesChanged ? "Recorded file tools. Files accessed inside shell commands may not be identified here." : "Recorded web tools. Search result links are not counted as fetched pages.")
                    }
                }
                if rows.isEmpty { Text(query.isEmpty ? "No recorded sources." : "No matching sources.").foregroundStyle(PhoneTheme.secondary).listRowBackground(PhoneTheme.surface) }
            }.listStyle(.insetGrouped).scrollContentBackground(.hidden).background(PhoneTheme.ground).foregroundStyle(PhoneTheme.ink)
                .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .automatic), prompt: "Find a source")
                .navigationTitle(kind.title).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
                    if kind == .filesRead || kind == .filesChanged { ToolbarItem(placement: .topBarLeading) { Button("Browse session files", systemImage: "folder", action: browseFiles).labelStyle(.iconOnly).accessibilityIdentifier("access.browse-files") } }
                }
        }
    }
}
private struct AccessDetail: View {
    let entry: AccessEntry
    let close: () -> Void
    let browseFiles: () -> Void
    private func safeURL(_ text: String) -> URL? {
        guard let url = URL(string: text), ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil, url.user == nil, url.password == nil else { return nil }
        return url
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(entry.target).font(.headline).textSelection(.enabled)
                if entry.operations > entry.events.count { Text("Showing the latest five of \(entry.operations) recorded actions.").font(.footnote).foregroundStyle(PhoneTheme.secondary) }
                ForEach(entry.events.reversed()) { event in
                    VStack(alignment: .leading, spacing: 14) {
                        Text(event.mode).font(.subheadline.weight(.semibold)).foregroundStyle(PhoneTheme.mint)
                        if let time = event.timestamp { Text(time.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(PhoneTheme.secondary) }
                        if !event.target.isEmpty && event.target != entry.target { Text("Requested: " + event.target).font(.caption).textSelection(.enabled) }
                        Text(event.preview).font(entry.kind == .filesRead || entry.kind == .filesChanged ? .system(.footnote, design: .monospaced) : .body).textSelection(.enabled)
                        ForEach(Array(event.links.enumerated()), id: \.offset) { _, link in
                            VStack(alignment: .leading, spacing: 6) {
                                if link.canOpen, let url = safeURL(link.url) { Link(link.title, destination: url).font(.subheadline.weight(.semibold)) }
                                else { Text(link.title).font(.subheadline.weight(.semibold)) }
                                Text(link.url).font(.caption).foregroundStyle(PhoneTheme.secondary).textSelection(.enabled)
                                if !link.snippet.isEmpty { Text(link.snippet).font(.footnote).textSelection(.enabled) }
                            }
                        }
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                }
                if entry.kind == .pages, let url = safeURL(entry.target) { Link("Open page", destination: url).font(.subheadline) }
                if entry.kind == .filesRead || entry.kind == .filesChanged {
                    Button("Browse session files", systemImage: "folder", action: browseFiles).font(.subheadline).accessibilityIdentifier("access.browse-files")
                    Text("Recorded excerpts show what the tool returned. Browse files to preview the current workspace contents.").font(.caption).foregroundStyle(PhoneTheme.secondary)
                }
            }.padding(20)
        }.foregroundStyle(PhoneTheme.ink).background(PhoneTheme.ground).navigationTitle("Source details").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done", action: close) } }
    }
}
