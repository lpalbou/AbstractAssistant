import SwiftUI
import WidgetKit

/// The Orb clock: the time told in particles round a small orb. The rim's sixty points light up as
/// the hour goes by (each minute a point, a few sparks round the lit ones), a comet of light circles
/// inside it as the hour hand, and the orb in the middle glows cyan, or amber with the number of
/// approvals and questions waiting for you. On a tinted face the lit points take the face's colour.
struct OrbClockDial: View {
    let date: Date
    var needYou = 0
    /// The number in the orb (a dial too small for it shows only the amber glow).
    var showsCount = true

    @Environment(\.widgetRenderingMode) private var mode

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            let t = Self.clock(date)
            ZStack {
                // The rim not yet lit, and the hours, faint.
                Dots(dots: Self.rim(minute: t.minute, lit: false) + Self.hourMarks).fill(.white.opacity(0.32))
                // The minutes gone by this hour, and their sparks.
                Dots(dots: Self.rim(minute: t.minute, lit: true)).fill(lit).widgetAccentable()
                // The hour: a comet circling inside the rim, its tail behind it.
                Dots(dots: Self.comet(hours: t.hours)).fill(comet).widgetAccentable()
                core(side)
            }
            .frame(width: side, height: side)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var full: Bool { mode == .fullColor }
    private var lit: Color { full ? Color(red: 0.36, green: 0.88, blue: 1) : .white }
    private var comet: Color { full ? Color(red: 0.86, green: 0.8, blue: 1) : .white }
    private var amber: Color { Color(red: 1, green: 0.66, blue: 0.2) }

    @ViewBuilder private func core(_ side: CGFloat) -> some View {
        let waiting = needYou > 0
        let glow = waiting ? amber : Color(red: 0.42, green: 0.5, blue: 1)
        ZStack {
            Circle()
                .fill(RadialGradient(colors: [.white, (full ? glow : .white).opacity(0.85), (full ? glow : .white).opacity(0)],
                                     center: .center, startRadius: 0, endRadius: side * 0.2))
                .frame(width: side * 0.4, height: side * 0.4)
            if waiting && showsCount {
                Text("\(min(needYou, 99))")
                    .font(.system(size: side * 0.2, weight: .heavy, design: .rounded))
                    .foregroundStyle(full ? Color.black.opacity(0.8) : .black)
                    .minimumScaleFactor(0.5)
            }
        }
        .widgetAccentable(waiting)
    }

    /// The minutes into the hour and the hours into the half day (fractions kept: the comet moves
    /// between the hours).
    static func clock(_ date: Date) -> (minute: Int, hours: Double) {
        let c = Calendar.current.dateComponents([.hour, .minute], from: date)
        let m = c.minute ?? 0
        return (m, Double((c.hour ?? 0) % 12) + Double(m) / 60)
    }

    /// A point on the dial: 0 at twelve o'clock, clockwise, `r` from the centre (1 = the edge).
    private static func at(_ turn: Double, _ r: Double, size: Double) -> Dot {
        let a = 2 * Double.pi * turn - Double.pi / 2
        return Dot(x: r * cos(a), y: r * sin(a), r: size)
    }

    /// Fixed noise, so a point keeps its place from one minute to the next.
    private static func noise(_ i: Int, _ salt: Double) -> Double {
        let v = sin(Double(i) * 12.9898 + salt * 78.233) * 43758.5453
        return v - v.rounded(.down)
    }

    /// The sixty points of the rim: the ones gone by this hour (`lit`), with the current minute the
    /// brightest and a few sparks round them, or the ones still to come.
    static func rim(minute: Int, lit: Bool) -> [Dot] {
        var dots: [Dot] = []
        for i in 0..<60 where (i <= minute) == lit {
            let turn = Double(i) / 60
            let r = 0.88 + 0.04 * (noise(i, 1) - 0.5)
            if !lit { dots.append(at(turn, r, size: i % 5 == 0 ? 0.03 : 0.02)); continue }
            dots.append(at(turn, r, size: i == minute ? 0.065 : 0.032 + 0.012 * noise(i, 2)))
            // Sparks: two tiny points drifting off each lit minute, fewer towards the start of the hour.
            for k in 0..<2 where noise(i, Double(3 + k)) < 0.35 + 0.5 * Double(i) / 60 {
                dots.append(at(turn + 0.006 * (noise(i, Double(5 + k)) - 0.5), r + 0.09 * (noise(i, Double(7 + k)) - 0.5), size: 0.012))
            }
        }
        return dots
    }

    static let hourMarks: [Dot] = (0..<12).map { at(Double($0) / 12, 0.7, size: $0 % 3 == 0 ? 0.022 : 0.014) }

    /// The hour hand: a stream of points from the orb out to a bright head at the hour, a short
    /// tail of light behind the head (it is moving round).
    static func comet(hours: Double) -> [Dot] {
        let turn = hours / 12
        let stream = (0..<7).map { k in at(turn, 0.25 + 0.05 * Double(k), size: 0.022 + 0.004 * Double(k)) }
        let head = at(turn, 0.6, size: 0.075)
        let tail = (1..<6).map { k in at(turn - 0.012 * Double(k), 0.6, size: 0.05 * pow(0.72, Double(k))) }
        return stream + [head] + tail
    }
}

/// One point of the dial, in units of the dial's radius from its centre.
struct Dot: Sendable {
    var x: Double, y: Double, r: Double
}

/// Points as one shape (one path to fill, however many points).
struct Dots: Shape {
    let dots: [Dot]
    func path(in rect: CGRect) -> Path {
        let R = Double(min(rect.width, rect.height)) / 2
        let cx = Double(rect.midX), cy = Double(rect.midY)
        var p = Path()
        for d in dots {
            p.addEllipse(in: CGRect(x: cx + d.x * R - d.r * R, y: cy + d.y * R - d.r * R, width: 2 * d.r * R, height: 2 * d.r * R))
        }
        return p
    }
}

/// The Orb clock on a rectangular slot (and in the Smart Stack): the dial, then what waits for you
/// and the next automation.
struct OrbClockCard: View {
    let date: Date
    let face: FaceSnapshot

    @Environment(\.widgetRenderingMode) private var mode

    var body: some View {
        HStack(spacing: 8) {
            OrbClockDial(date: date, needYou: face.needYou)
                .frame(width: 46, height: 46)
            VStack(alignment: .leading, spacing: 1) {
                Text(headline)
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

    private var headline: String {
        switch face.needYou {
        case 0: "All clear"
        case 1: "1 needs you"
        default: "\(face.needYou) need you"
        }
    }

    private var second: String? {
        if face.needYou > 0 { return face.firstNeed }
        return face.newResults > 0 ? (face.newResults == 1 ? "1 new result" : "\(face.newResults) new results") : nil
    }
}

/// One line of text (the inline slot, the corner's label): what waits for you, else the next automation.
struct OrbClockLine {
    static func text(_ face: FaceSnapshot, at date: Date) -> Text {
        if face.needYou > 0 { return Text(face.needYou == 1 ? "1 needs you" : "\(face.needYou) need you") }
        if let next = face.next(after: date) { return Text("\(next.name) in \(FaceSnapshot.inShort(next.at, from: date))") }
        return Text("All clear")
    }
}
