import SwiftUI
import WidgetKit

/// The Assistant's complication: your avatar, on every slot a face offers.
@main
struct AssistantComplications: WidgetBundle {
    var body: some Widget { AvatarWidget() }
}

struct AvatarEntry: TimelineEntry {
    let date: Date
    let face: FaceSnapshot
}

/// What the app last said, redrawn every five minutes for two hours (the next automation counts
/// down); the app asks for a new timeline whenever what it shows changes.
struct AvatarProvider: TimelineProvider {
    func placeholder(in context: Context) -> AvatarEntry { AvatarEntry(date: Date(), face: .sample) }

    func getSnapshot(in context: Context, completion: @escaping (AvatarEntry) -> Void) {
        completion(AvatarEntry(date: Date(), face: context.isPreview ? .sample : FaceSnapshot.read()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<AvatarEntry>) -> Void) {
        let face = FaceSnapshot.read()
        let start = Date()
        let entries = (0..<24).map { AvatarEntry(date: start.addingTimeInterval(Double($0) * 300), face: face) }
        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

struct AvatarWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: FaceSnapshot.kind, provider: AvatarProvider()) { entry in
            AvatarEntryView(entry: entry)
        }
        .configurationDisplayName("Assistant")
        .description("Your assistant's avatar, and what needs you.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryCorner, .accessoryInline])
    }
}

struct AvatarEntryView: View {
    let entry: AvatarEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        content.containerBackground(for: .widget) { Color.clear }
    }

    @ViewBuilder private var content: some View {
        switch family {
        case .accessoryRectangular:
            FaceCard(date: entry.date, face: entry.face)
        case .accessoryCorner:
            FaceAvatar(needYou: entry.face.needYou, showsCount: false)
                .widgetLabel { FaceLine.text(entry.face, at: entry.date) }
        case .accessoryInline:
            Label { FaceLine.text(entry.face, at: entry.date) } icon: { Image(systemName: "circle.hexagongrid.fill") }
        default:
            ZStack {
                AccessoryWidgetBackground()
                FaceAvatar(needYou: entry.face.needYou)
            }
        }
    }
}
