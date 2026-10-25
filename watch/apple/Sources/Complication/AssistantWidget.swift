import SwiftUI
import WidgetKit

/// The Assistant's complication: the app's blue orb, on every slot a face offers.
@main
struct AssistantComplications: WidgetBundle {
    var body: some Widget { AssistantWidget() }
}

struct AssistantEntry: TimelineEntry {
    let date: Date
    let face: FaceSnapshot
}

/// What the app last said, redrawn every five minutes for two hours (the next automation counts
/// down); the app asks for a new timeline whenever what it shows changes.
struct AssistantProvider: TimelineProvider {
    func placeholder(in context: Context) -> AssistantEntry { AssistantEntry(date: Date(), face: FaceSnapshot.read()) }

    func getSnapshot(in context: Context, completion: @escaping (AssistantEntry) -> Void) {
        completion(AssistantEntry(date: Date(), face: FaceSnapshot.read()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<AssistantEntry>) -> Void) {
        let face = FaceSnapshot.read()
        let start = Date()
        let entries = (0..<24).map { AssistantEntry(date: start.addingTimeInterval(Double($0) * 300), face: face) }
        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

struct AssistantWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: FaceSnapshot.kind, provider: AssistantProvider()) { entry in
            AssistantEntryView(entry: entry)
        }
        .configurationDisplayName("Assistant")
        .description("Your assistant's avatar, and what needs you.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryCorner, .accessoryInline])
    }
}

struct AssistantEntryView: View {
    let entry: AssistantEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        content.containerBackground(for: .widget) { Color.clear }
    }

    @ViewBuilder private var content: some View {
        switch family {
        case .accessoryRectangular:
            FaceCard(date: entry.date, face: entry.face)
        case .accessoryCorner:
            FaceOrb(face: entry.face, showsCount: false)
                .widgetLabel { FaceLine.text(entry.face, at: entry.date) }
        case .accessoryInline:
            Label { FaceLine.text(entry.face, at: entry.date) } icon: { Image(systemName: "circle.hexagongrid.fill") }
        default:
            // No disc behind it: the picture fills the circle, and on a face in one tint a disc
            // would wash its light out.
            FaceOrb(face: entry.face)
        }
    }
}
