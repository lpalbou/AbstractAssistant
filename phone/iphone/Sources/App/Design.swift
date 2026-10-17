import SwiftUI
import AbstractGatewayClient

enum PhoneTheme {
    static let ground = Color(red: 0.035, green: 0.045, blue: 0.085)
    static let surface = Color(red: 0.075, green: 0.09, blue: 0.15)
    static let ink = Color(red: 0.93, green: 0.95, blue: 1)
    static let secondary = Color(red: 0.65, green: 0.70, blue: 0.80)
    static let lavender = Color(red: 0.68, green: 0.65, blue: 1)
    static let mint = Color(red: 0.42, green: 0.89, blue: 0.80)
    static let amber = Color(red: 1, green: 0.77, blue: 0.43)
    static var stroke: Color { .white.opacity(0.09) }
}

struct NavigationCaption: View {
    let title: String
    var demo: Bool
    var body: some View {
        VStack(spacing: 1) {
            Text(title).font(.headline)
            if demo { Text("DEMO").font(.system(size: 9, weight: .semibold, design: .rounded)).tracking(2).foregroundStyle(PhoneTheme.secondary) }
        }
    }
}

/// Local audio energy changes the silhouette, ring spacing, light and halo together.
struct AssistantOrb: View {
    var size: CGFloat = 88
    var active = false
    var level: Double = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        TimelineView(.animation(minimumInterval: active ? 1.0 / 30 : 1.0 / 12, paused: reduceMotion || scenePhase != .active)) { frame in
            let time = reduceMotion ? 0 : frame.date.timeIntervalSinceReferenceDate
            let energy = level.isFinite ? min(1, max(0, level)) : 0
            let motionEnergy = reduceMotion ? 0 : energy
            let breath = reduceMotion ? 0 : sin(time * 0.85) * 0.018
            ZStack {
                Circle().fill(PhoneTheme.mint.opacity(0.10 + energy * 0.28)).blur(radius: size * 0.14).padding(-size * (0.04 + energy * 0.12))
                Circle().fill(RadialGradient(colors: [PhoneTheme.mint.opacity(0.30 + energy * 0.35), PhoneTheme.lavender.opacity(0.28), PhoneTheme.ground], center: .init(x: 0.32, y: 0.28), startRadius: 1, endRadius: size * 0.67))
                ForEach(0..<5) { index in
                    Ellipse().stroke(AngularGradient(colors: [.clear, PhoneTheme.mint.opacity(0.8), PhoneTheme.lavender, PhoneTheme.mint.opacity(0.9), .clear], center: .center), lineWidth: (index == 2 ? 1.5 : 0.7) + energy * 1.5)
                        .frame(width: size * (0.58 + Double(index) * 0.075 + motionEnergy * 0.08), height: size * (0.43 + motionEnergy * 0.14))
                        .rotationEffect(.degrees(Double(index) * 34 + time * 9 + motionEnergy * Double(index - 2) * 13))
                }
                Circle().stroke(PhoneTheme.lavender.opacity(0.28 + energy * 0.42), lineWidth: 0.8 + energy)
            }
            .frame(width: size, height: size)
            .scaleEffect(reduceMotion ? 1 : 1 + breath + energy * 0.20)
            .shadow(color: PhoneTheme.mint.opacity(energy * 0.6), radius: 5 + energy * 18)
            .animation(reduceMotion ? nil : .linear(duration: 0.055), value: energy)
        }.frame(width: size, height: size).accessibilityHidden(true)
    }
}

struct PhoneCard<Content: View>: View {
    @ViewBuilder var content: () -> Content
    var body: some View {
        content().padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 22))
            .overlay(RoundedRectangle(cornerRadius: 22).stroke(PhoneTheme.stroke))
    }
}

struct QuietLabel: View {
    let text: String
    var color: Color = PhoneTheme.secondary
    var body: some View { Text(text.uppercased()).font(.system(.caption2, design: .rounded, weight: .semibold)).tracking(2).foregroundStyle(color) }
}

struct PhoneMarkdown: View {
    let text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Array(MarkdownBlock.parse(text).enumerated()), id: \.offset) { _, item in block(item) }
        }.font(.body).lineSpacing(5).textSelection(.enabled).tint(PhoneTheme.mint).frame(maxWidth: .infinity, alignment: .leading)
    }
    private func inline(_ value: String) -> AttributedString {
        (try? AttributedString(markdown: value, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(value)
    }
    @ViewBuilder private func block(_ item: MarkdownBlock) -> some View {
        switch item {
        case .heading(let level, let value): Text(inline(value)).font(level < 3 ? .title3.weight(.semibold) : .headline).padding(.top, 5)
        case .paragraph(let value): Text(inline(value))
        case .item(let marker, let depth, let value):
            HStack(alignment: .top, spacing: 10) { Text(marker).foregroundStyle(PhoneTheme.lavender); Text(inline(value)).frame(maxWidth: .infinity, alignment: .leading) }.padding(.leading, CGFloat(depth) * 14)
        case .quote(let value):
            Text(inline(value)).foregroundStyle(PhoneTheme.secondary).padding(.leading, 15)
                .overlay(alignment: .leading) { RoundedRectangle(cornerRadius: 2).fill(PhoneTheme.lavender).frame(width: 3) }
        case .code(let value): ScrollView(.horizontal) { Text(value).font(.system(.footnote, design: .monospaced)).padding(14) }.background(PhoneTheme.surface, in: RoundedRectangle(cornerRadius: 12))
        case .rule: Divider().overlay(PhoneTheme.stroke)
        case .table(let rows):
            ScrollView(.horizontal) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(rows.indices, id: \.self) { row in
                        HStack(alignment: .top, spacing: 0) { ForEach(rows[row].indices, id: \.self) { column in Text(inline(rows[row][column])).font(row == 0 ? .subheadline.weight(.semibold) : .subheadline).frame(width: 160, alignment: .leading).padding(10) } }
                            .background(row == 0 ? PhoneTheme.lavender.opacity(0.10) : .clear)
                        Divider()
                    }
                }
            }
        }
    }
}

struct ErrorBanner: View {
    let message: String
    var dismiss: (() -> Void)? = nil
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "wifi.exclamationmark").foregroundStyle(PhoneTheme.amber)
            Text(message).font(.footnote).fixedSize(horizontal: false, vertical: true)
            if let dismiss { Button(action: dismiss) { Image(systemName: "xmark").frame(width: 32, height: 32) }.accessibilityLabel("Dismiss message") }
        }.padding(14).background(PhoneTheme.amber.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
    }
}


/// Only this small subtree observes the audio envelope, keeping message layout out of the meter loop.
struct VoicePresence: View {
    let voice: VoiceController
    var working: Bool
    var enabled: Bool
    var onPress: () -> Void
    var onRelease: () -> Void
    var onCancel: () -> Void
    var onAccessibleActivate: () -> Void
    private var status: String {
        switch voice.inputPhase {
        case .authorizing: return "Microphone…"
        case .recording: return "Listening"
        case .atLimit: return "Release to send"
        case .countdown: return "Tap to cancel"
        case .ready, .transcribing: return "Transcribing"
        case .idle: return voice.speaking ? (voice.paused ? "Reading paused" : "Reading aloud") : working ? "Thinking" : "Hold to speak"
        }
    }
    var body: some View {
        VStack(spacing: 7) {
            ZStack {
                AssistantOrb(size: 72, active: voice.recording || voice.speaking || working, level: voice.meter.level)
                if voice.inputPhase == .countdown {
                    Circle().trim(from: 0, to: voice.meter.graceProgress).stroke(PhoneTheme.mint, style: StrokeStyle(lineWidth: 2.5, lineCap: .round)).rotationEffect(.degrees(-90)).frame(width: 84, height: 84)
                    Text("\(voice.secondsRemaining)").font(.system(.title2, design: .rounded, weight: .medium)).contentTransition(.numericText(countsDown: true))
                }
                OrbTouchSurface(enabled: enabled, label: status, onPress: onPress, onRelease: onRelease, onCancel: onCancel, onAccessibleActivate: onAccessibleActivate)
                    .frame(width: 98, height: 92)
            }.frame(height: 92)
            Text(status).font(.system(.caption2, design: .rounded, weight: .medium)).foregroundStyle(voice.localPending ? PhoneTheme.mint : PhoneTheme.secondary).lineLimit(1).minimumScaleFactor(0.75)
        }.frame(width: 98)
    }
}
