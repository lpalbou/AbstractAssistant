import SwiftUI
import WidgetKit

/// The Assistant's complications: the Orb clock, on every slot a face offers.
@main
struct AssistantComplications: WidgetBundle {
    var body: some Widget { OrbClockWidget() }
}

struct OrbClockEntry: TimelineEntry {
    let date: Date
    let face: FaceSnapshot
}

/// A dial a minute for the next hour, from what the app last said; the app asks for a new timeline
/// whenever that changes.
struct OrbClockProvider: TimelineProvider {
    func placeholder(in context: Context) -> OrbClockEntry { OrbClockEntry(date: Date(), face: .sample) }

    func getSnapshot(in context: Context, completion: @escaping (OrbClockEntry) -> Void) {
        completion(OrbClockEntry(date: Date(), face: context.isPreview ? .sample : FaceSnapshot.read()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<OrbClockEntry>) -> Void) {
        let face = FaceSnapshot.read()
        let start = Calendar.current.dateInterval(of: .minute, for: Date())?.start ?? Date()
        let entries = (0..<60).map { OrbClockEntry(date: start.addingTimeInterval(Double($0) * 60), face: face) }
        completion(Timeline(entries: entries, policy: .atEnd))
    }
}

struct OrbClockWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: FaceSnapshot.kind, provider: OrbClockProvider()) { entry in
            OrbClockEntryView(entry: entry)
        }
        .configurationDisplayName("Orb clock")
        .description("The time in particles round your assistant's orb, and what needs you.")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryCorner, .accessoryInline])
    }
}

struct OrbClockEntryView: View {
    let entry: OrbClockEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        content.containerBackground(for: .widget) { Color.clear }
    }

    @ViewBuilder private var content: some View {
        switch family {
        case .accessoryRectangular:
            OrbClockCard(date: entry.date, face: entry.face)
        case .accessoryCorner:
            OrbClockDial(date: entry.date, needYou: entry.face.needYou, showsCount: false)
                .widgetLabel { OrbClockLine.text(entry.face, at: entry.date) }
        case .accessoryInline:
            Label { OrbClockLine.text(entry.face, at: entry.date) } icon: { Image(systemName: "circle.hexagongrid.fill") }
        default:
            ZStack {
                AccessoryWidgetBackground()
                OrbClockDial(date: entry.date, needYou: entry.face.needYou).padding(2)
            }
        }
    }
}
