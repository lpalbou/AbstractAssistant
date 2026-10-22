import AbstractGatewayClient
import SwiftUI
import WatchKit

/// The clock: the app as a watch face. Your orb, alive, in the middle of a dial of particles: the
/// rim's sixty points light up as the hour goes by, the hour is a comet orbiting the orb. The
/// corners: the date (top left; the watch's own time is top right), what waits for you (bottom
/// left, amber) and the next automation (bottom right). A tap on the orb talks, as on Home. Swiped
/// to from Home (to the left), and back (to the right); Settings → Start on the clock opens the app
/// on it. Wrist down (always on), the orb holds still and the dial dims, redrawn every minute.
struct ClockFaceView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.isLuminanceReduced) private var dimmed

    var body: some View {
        GeometryReader { geo in
            let screen = WKInterfaceDevice.current().screenBounds.size
            let side = min(screen.width, screen.height) - 10
            TimelineView(.everyMinute) { ctx in
                ZStack {
                    FaceDial(date: ctx.date, dimmed: dimmed)
                        .frame(width: side, height: side)
                        .allowsHitTesting(false)
                    orb(side)
                    corners(ctx.date)
                }
                .frame(width: screen.width, height: screen.height)
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        .ignoresSafeArea()
        .background(Color.black.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .containerBackground(Color.black, for: .navigation)
    }

    private func orb(_ side: CGFloat) -> some View {
        Button { model.newAskSession(); model.openOrb() } label: {
            Orb(mode: .idle, size: side * 0.56, fps: 24, look: model.responderLook)
                .frame(width: side * 0.6, height: side * 0.6)
                .contentShape(Circle())
        }
        .buttonStyle(.tap)
        .accessibilityLabel("Talk to \(model.responder.title)")
        .accessibilityIdentifier("clock.orb")
    }

    @ViewBuilder private func corners(_ now: Date) -> some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: -2) {
                    Text(now.formatted(.dateTime.weekday(.abbreviated)).uppercased())
                        .font(.rounded(.caption2, weight: .semibold)).foregroundStyle(dimmed ? Theme.muted : Theme.cyan)
                    Text(now.formatted(.dateTime.day()))
                        .font(.rounded(.title3, weight: .semibold)).foregroundStyle(dimmed ? Theme.muted : Theme.text)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("clock.date")
                Spacer()
            }
            Spacer()
            HStack(alignment: .bottom) {
                needYou
                Spacer()
                nextAutomation(now)
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 14)
        .padding(.bottom, 10)
    }

    /// What waits for you: its number in amber; a tap opens it (the one, or the list).
    @ViewBuilder private var needYou: some View {
        if !model.waits.isEmpty {
            Button {
                if model.waits.count == 1, let w = model.waits.first { model.push(w.kind == .askUser ? .askUser(w) : .approval(w)) }
                else { model.push(.waits) }
            } label: {
                Text("\(model.waits.count)")
                    .font(.rounded(.headline, weight: .heavy)).foregroundStyle(.black)
                    .frame(minWidth: 30, minHeight: 30)
                    .background(Circle().fill(dimmed ? Theme.amber.opacity(0.5) : Theme.amber))
                    .padding(6).contentShape(Rectangle())
            }
            .buttonStyle(.tap)
            .accessibilityLabel(model.waits.count == 1 ? "1 needs you" : "\(model.waits.count) need you")
            .accessibilityIdentifier("clock.needYou")
        }
    }

    /// The next automation to run: how long until it, its name below; a tap opens it.
    @ViewBuilder private func nextAutomation(_ now: Date) -> some View {
        let next = model.automations.filter { $0.status == "active" }
            .compactMap { a in a.nextFireAt.flatMap(ISO8601.date).map { (a, $0) } }
            .filter { $0.1 > now }
            .min { $0.1 < $1.1 }
        if let (a, at) = next {
            Button { model.push(.automations); model.push(.automation(a)) } label: {
                VStack(alignment: .trailing, spacing: -1) {
                    Text(FaceSnapshot.inShort(at, from: now))
                        .font(.rounded(.headline, weight: .semibold)).foregroundStyle(dimmed ? Theme.muted : Theme.text)
                    Text(a.name ?? "Automation")
                        .font(.rounded(.caption2)).foregroundStyle(Theme.muted).lineLimit(1)
                }
                .frame(maxWidth: 70, alignment: .trailing)
                .padding(6).contentShape(Rectangle())
            }
            .buttonStyle(.tap)
            .accessibilityLabel("\(a.name ?? "An automation") in \(FaceSnapshot.inShort(at, from: now))")
            .accessibilityIdentifier("clock.next")
        }
    }
}

/// The dial round the orb: the rim's minutes lit through the hour (sparks round the lit ones, the
/// current minute brightest), the twelve hours, and the hour as a comet orbiting the orb.
struct FaceDial: View {
    let date: Date
    var dimmed = false

    var body: some View {
        let t = OrbClockDial.clock(date)
        ZStack {
            Dots(dots: OrbClockDial.rim(minute: t.minute, lit: false, radius: 0.93, scale: 0.5)).fill(.white.opacity(dimmed ? 0.18 : 0.28))
            Dots(dots: Self.hours).fill(.white.opacity(dimmed ? 0.3 : 0.55))
            Dots(dots: OrbClockDial.rim(minute: t.minute, lit: true, radius: 0.93, scale: 0.55))
                .fill(Color(red: 0.36, green: 0.88, blue: 1).opacity(dimmed ? 0.45 : 1))
            Dots(dots: Self.comet(hours: t.hours)).fill(Color(red: 0.86, green: 0.8, blue: 1).opacity(dimmed ? 0.5 : 1))
        }
    }

    /// The twelve hours: a little longer line of points at twelve, three, six and nine.
    static let hours: [Dot] = (0..<12).flatMap { h -> [Dot] in
        let turn = Double(h) / 12, a = 2 * Double.pi * turn - Double.pi / 2
        let n = h % 3 == 0 ? 3 : 1
        return (0..<n).map { k in let r = 0.84 - 0.03 * Double(k); return Dot(x: r * cos(a), y: r * sin(a), r: h % 3 == 0 ? 0.011 : 0.008) }
    }

    /// The hour: a bright head on the orb's orbit, its tail of light behind it.
    static func comet(hours: Double) -> [Dot] {
        let turn = hours / 12
        return (0..<12).map { k in
            let a = 2 * Double.pi * (turn - 0.008 * Double(k)) - Double.pi / 2
            let r = 0.74
            return Dot(x: r * cos(a), y: r * sin(a), r: 0.034 * pow(0.8, Double(k)))
        }
    }
}
