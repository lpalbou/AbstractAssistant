import SwiftUI
import UIKit
import WidgetKit

/// Your avatar on the watch face: the orb style you chose, as the app last drew it (a soft cyan glow
/// until it has), and, when approvals or questions wait for you, their number on an amber badge.
struct FaceAvatar: View {
    var needYou = 0
    /// The badge (a slot too small for it shows the avatar alone).
    var showsCount = true

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            ZStack(alignment: .bottomTrailing) {
                picture(side)
                if needYou > 0 && showsCount {
                    Text("\(min(needYou, 99))")
                        .font(.system(size: side * 0.26, weight: .heavy, design: .rounded))
                        .foregroundStyle(.black)
                        .minimumScaleFactor(0.5)
                        .frame(width: side * 0.4, height: side * 0.4)
                        .background(Circle().fill(Color(red: 1, green: 0.66, blue: 0.2)))
                        .widgetAccentable()
                }
            }
            .frame(width: side, height: side)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder private func picture(_ side: CGFloat) -> some View {
        if let data = FaceSnapshot.avatar(), let image = UIImage(data: data) {
            Image(uiImage: image)
                .resizable()
                .widgetAccentedRenderingMode(.fullColor)
                .scaledToFit()
                .clipShape(Circle())
        } else {
            Circle()
                .fill(RadialGradient(colors: [.white, Color(red: 0.36, green: 0.7, blue: 1).opacity(0.8), .clear],
                                     center: .center, startRadius: 0, endRadius: side * 0.45))
        }
    }
}

/// The rectangular slot (and the Smart Stack): the avatar, then what waits for you, else the
/// results not seen, and the next automation.
struct FaceCard: View {
    let date: Date
    let face: FaceSnapshot

    @Environment(\.widgetRenderingMode) private var mode

    var body: some View {
        HStack(spacing: 8) {
            FaceAvatar(needYou: face.needYou, showsCount: false)
                .frame(width: 46, height: 46)
            VStack(alignment: .leading, spacing: 1) {
                Text(FaceLine.needYou(face) ?? "All clear")
                    .font(.system(.headline, design: .rounded))
                    .foregroundStyle(face.needYou > 0 && mode == .fullColor ? Color(red: 1, green: 0.66, blue: 0.2) : .primary)
                    .widgetAccentable(face.needYou > 0)
                if let second { Text(second).font(.system(.footnote, design: .rounded)).foregroundStyle(.secondary) }
                if let next = face.next(after: date) {
                    Text("\(next.name) · \(FaceSnapshot.inShort(next.at, from: date))").font(.system(.footnote, design: .rounded)).foregroundStyle(.secondary)
                }
            }
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            Spacer(minLength: 0)
        }
    }

    private var second: String? {
        if face.needYou > 0 { return face.firstNeed }
        return face.newResults > 0 ? (face.newResults == 1 ? "1 new result" : "\(face.newResults) new results") : nil
    }
}

/// One line of text (the inline slot, the corner's label): what waits for you, else the next
/// automation, else "All clear".
enum FaceLine {
    static func needYou(_ face: FaceSnapshot) -> String? {
        switch face.needYou {
        case 0: nil
        case 1: "1 needs you"
        default: "\(face.needYou) need you"
        }
    }

    static func text(_ face: FaceSnapshot, at date: Date) -> Text {
        if let n = needYou(face) { return Text(n) }
        if let next = face.next(after: date) { return Text("\(next.name) in \(FaceSnapshot.inShort(next.at, from: date))") }
        return Text("All clear")
    }
}
