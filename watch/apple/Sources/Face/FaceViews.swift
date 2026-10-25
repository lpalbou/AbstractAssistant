import SwiftUI
import UIKit
import WidgetKit

/// Your avatar on the watch face: the orb style you chose, as the app last drew it (the app's own
/// orb until it has), in the face's state: at rest; speaking with a dot when there is news
/// (results or messages not seen); listening with the number of approvals and questions waiting
/// for you. Never greyed out (the face's gallery and a locked watch grey out what a complication
/// shows; the avatar and a count hide nothing). A face that draws its complications in one tint
/// shows the orb's light in that tint (its picture as a mask), not a flat disc.
struct FaceOrb: View {
    var face = FaceSnapshot()
    /// The badge (a slot too small for it shows the avatar alone, with the dot for news).
    var showsCount = true

    @Environment(\.widgetRenderingMode) private var mode
    @Environment(\.displayScale) private var scale

    private static let amber = Color(red: 1, green: 0.66, blue: 0.2)
    private static let cyan = Color(red: 0.36, green: 0.7, blue: 1)

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            picture(side)
                .overlay(alignment: .bottomTrailing) { if face.needYou > 0 && showsCount { badge(side) } }
                .overlay(alignment: .topTrailing) { if face.state == .news { dot(side) } }
                .frame(width: side, height: side)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .unredacted()
    }

    /// The number waiting for you: on amber; on a face in one tint, a ring in its accent round the
    /// number (a filled disc would hide it, every colour being the face's own there).
    @ViewBuilder private func badge(_ side: CGFloat) -> some View {
        let number = Text("\(min(face.needYou, 99))")
            .font(.system(size: side * 0.26, weight: .heavy, design: .rounded))
            .minimumScaleFactor(0.5)
            .frame(width: side * 0.4, height: side * 0.4)
        if mode == .accented {
            number.foregroundStyle(.primary)
                .overlay(Circle().strokeBorder(lineWidth: max(1.5, side * 0.045)).widgetAccentable())
        } else {
            number.foregroundStyle(.black)
                .background(Circle().fill(Self.amber))
                .widgetAccentable()
        }
    }

    /// News: a dot, cyan (the face's accent in one tint).
    private func dot(_ side: CGFloat) -> some View {
        Circle().fill(Self.cyan)
            .frame(width: side * 0.22, height: side * 0.22)
            .overlay { if mode != .accented { Circle().strokeBorder(.black.opacity(0.7), lineWidth: 1) } }
            .widgetAccentable()
            .accessibilityLabel("News")
    }

    @ViewBuilder private func picture(_ side: CGFloat) -> some View {
        if mode == .accented {
            // One tint: the orb's light as transparency, in the face's accent.
            fitted(FaceSnapshot.avatar(face.state, mask: true).flatMap(UIImage.init(data:)) ?? UIImage(named: "OrbMask"), side)
                .renderingMode(.template)
                .resizable()
                .scaledToFit()
                .clipShape(Circle())
                .widgetAccentable()
        } else {
            fitted(FaceSnapshot.avatar(face.state).flatMap(UIImage.init(data:)) ?? UIImage(named: "Orb"), side)
                .resizable()
                .widgetAccentedRenderingMode(.fullColor)
                .scaledToFit()
                .clipShape(Circle())
        }
    }

    /// The picture at the slot's own size in pixels (a face refuses a complication whose picture
    /// is much larger than its slot: the avatar is drawn at 240 px, a slot is about 100 px).
    private func fitted(_ image: UIImage?, _ side: CGFloat) -> Image {
        guard let cg = image?.cgImage else { return Image(systemName: "circle.fill") }
        let px = Int(min(160, max(8, (side * scale).rounded(.up))))
        let w = px, h = max(1, px * cg.height / max(1, cg.width))
        guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return Image(uiImage: UIImage(cgImage: cg))
        }
        ctx.interpolationQuality = .high
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        return Image(uiImage: UIImage(cgImage: ctx.makeImage() ?? cg))
    }
}

/// The rectangular slot (and the Smart Stack): the orb, then what waits for you, else the
/// results not seen, and the next automation.
struct FaceCard: View {
    let date: Date
    let face: FaceSnapshot

    @Environment(\.widgetRenderingMode) private var mode

    var body: some View {
        HStack(spacing: 8) {
            FaceOrb(face: face, showsCount: false)
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
