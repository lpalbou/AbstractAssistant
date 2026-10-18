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
    static let tool = lavender
    static let approval = amber
    static var stroke: Color { .white.opacity(0.09) }
}

struct NavigationCaption: View {
    let title: String
    var demo: Bool
    var titleWidth: CGFloat? = nil
    var body: some View {
        VStack(spacing: 1) {
            Text(title).font(.headline).lineLimit(1).truncationMode(.tail).frame(width: titleWidth)
            if demo { Text("DEMO").font(.system(size: 9, weight: .semibold, design: .rounded)).tracking(2).foregroundStyle(PhoneTheme.secondary) }
        }
    }
}

/// The same contour morphs between the listening orb and the agent's stop control.
struct OrbContour: Shape {
    var squareness: Double = 0
    var energy: Double = 0
    var phase: Double = 0
    var ribbon = false
    var animatableData: AnimatablePair<Double, Double> {
        get { .init(squareness, energy) }
        set { squareness = newValue.first; energy = newValue.second }
    }
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let exponent = 2 / (2 + 5 * squareness)
        for step in 0...120 {
            let angle = Double(step) / 120 * .pi * 2
            let x = cos(angle), y = sin(angle)
            let ripple = ribbon ? energy * (0.19 * sin(3 * angle + phase) + 0.075 * sin(7 * angle - phase)) : 0
            let radius = 0.5 * (1 + ripple)
            let point = CGPoint(x: rect.midX + rect.width * radius * (x < 0 ? -1 : 1) * pow(abs(x), exponent),
                                y: rect.midY + rect.height * radius * (y < 0 ? -1 : 1) * pow(abs(y), exponent))
            if step == 0 { path.move(to: point) } else { path.addLine(to: point) }
        }
        path.closeSubpath(); return path
    }
}

/// Animate the presentation outside TimelineView so audio/clock updates cannot snap the morph.
struct AssistantOrb: View {
    var size: CGFloat = 88
    var active = false
    var level: Double = 0
    var working = false
    var listening = false
    var animationTime: TimeInterval? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        OrbArtwork(size: size, stopProgress: working ? 1 : 0, active: active, level: level,
                   listening: listening, animationTime: animationTime, reduceMotion: reduceMotion,
                   paused: scenePhase != .active)
            .animation(reduceMotion ? nil : .timingCurve(0.4, 0, 0.2, 1, duration: 0.65), value: working)
            .frame(width: size, height: size).accessibilityHidden(true)
    }
}

/// A single interpolated value shapes the shell, ribbons, light and stop mark in both directions.
struct OrbArtwork: View, Animatable {
    var size: CGFloat
    nonisolated var stopProgress: Double
    var active = false
    var level: Double = 0
    var listening = false
    var animationTime: TimeInterval? = nil
    var reduceMotion = false
    var paused = false
    nonisolated var animatableData: Double {
        get { stopProgress }
        set { stopProgress = newValue }
    }
    var body: some View {
        TimelineView(.animation(minimumInterval: active ? (stopProgress > 0 ? 1.0 / 30 : 1.0 / 60) : 1.0 / 12,
                                paused: reduceMotion || paused)) { frame in
            OrbFrame(size: size, stopProgress: stopProgress, level: level, listening: listening,
                     time: reduceMotion ? 0 : animationTime ?? frame.date.timeIntervalSinceReferenceDate,
                     reduceMotion: reduceMotion)
        }
    }
}

/// Only real microphone/playback levels deform the ribbons; working adds a quiet pulse of light.
struct OrbFrame: View {
    var size: CGFloat
    var stopProgress: Double
    var level: Double = 0
    var listening = false
    var time: TimeInterval
    var reduceMotion = false
    var body: some View {
        let progress = min(1, max(0, stopProgress))
        let energy = level.isFinite ? min(1, max(0, level)) : 0
        let motionEnergy = reduceMotion ? 0 : energy
        let pulse = reduceMotion ? 0 : sin(time * 1.8)
        let breath = reduceMotion ? 0 : sin(time * 0.85) * 0.018
        let shape = OrbContour(squareness: progress)
        ZStack {
            shape.fill(PhoneTheme.mint.opacity(0.10 + energy * 0.32 + progress * (0.10 + pulse * 0.035)))
                .blur(radius: size * 0.14).padding(-size * (0.04 + energy * 0.09))
            shape.fill(RadialGradient(colors: [PhoneTheme.mint.opacity(0.30 + energy * 0.35 + progress * 0.16),
                                             PhoneTheme.lavender.opacity(0.28 + progress * 0.16), PhoneTheme.ground],
                                      center: .init(x: 0.32, y: 0.28), startRadius: 1, endRadius: size * 0.8))
            ForEach(0..<5) { index in
                OrbContour(squareness: progress, energy: motionEnergy,
                           phase: time * 3 + Double(index) * 1.7 + (listening ? motionEnergy * 3 : 0), ribbon: true)
                    .stroke(AngularGradient(colors: [.clear, PhoneTheme.mint.opacity(0.8), PhoneTheme.lavender,
                                                     PhoneTheme.mint.opacity(0.9), .clear], center: .center),
                            lineWidth: (index == 2 ? 1.4 : 0.75) + energy * 1.9 + progress * 0.3)
                    .frame(width: size * (0.53 + Double(index) * 0.055 + motionEnergy * 0.16),
                           height: size * (0.39 + motionEnergy * 0.33 + progress * 0.16))
                    .rotationEffect(.degrees(Double(index) * 34 + time * 9 + motionEnergy * Double(index - 2) * 28))
            }
            shape.stroke(PhoneTheme.lavender.opacity(0.28 + energy * 0.42 + progress * 0.35),
                         lineWidth: 0.8 + energy + progress * 0.5)
            shape.stroke(AngularGradient(colors: [PhoneTheme.mint.opacity(0.95), PhoneTheme.lavender.opacity(0.25),
                                                   PhoneTheme.lavender, PhoneTheme.mint.opacity(0.95)],
                                         center: .center, angle: .degrees(time * 28)), lineWidth: 1.3)
                .opacity(progress)
            // A dark inset keeps the familiar stop symbol legible over moving ribbons.
            RoundedRectangle(cornerRadius: size * 0.12)
                .fill(PhoneTheme.ground.opacity(0.90))
                .overlay(RoundedRectangle(cornerRadius: size * 0.12).stroke(PhoneTheme.mint.opacity(0.28)))
                .frame(width: size * 0.46, height: size * 0.46)
                .overlay {
                    RoundedRectangle(cornerRadius: size * 0.045)
                        .fill(LinearGradient(colors: [PhoneTheme.mint, PhoneTheme.lavender],
                                             startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: size * 0.25, height: size * 0.25)
                }
                .opacity(progress).scaleEffect(0.65 + progress * 0.35)
        }
        .frame(width: size, height: size)
        .scaleEffect((1 - progress * 0.04) * (1 + breath + motionEnergy * 0.08))
        .shadow(color: PhoneTheme.mint.opacity(energy * 0.6 + progress * 0.18), radius: 5 + energy * 14)
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
    var generatedMedia: MessageMediaController? = nil
    var working: Bool
    var stopping: Bool
    var enabled: Bool
    var onTap: () -> Void
    var onCancel: () -> Void
    var onStop: () -> Void
    private var status: String {
        if working { return stopping ? "Stopping assistant" : "Stop assistant" }
        switch voice.inputPhase {
        case .authorizing: return "Starting microphone"
        case .recording: return "Listening. Tap to cancel"
        case .countdown: return "Sending in \(voice.secondsRemaining) seconds. Tap to cancel"
        case .ready, .transcribing: return "Transcribing. Tap to cancel"
        case .idle: return voice.speaking ? "Reading aloud. Tap to speak" : working ? "Thinking" : "Tap to speak"
        }
    }
    var body: some View {
        ZStack {
            AssistantOrb(size: 68, active: voice.recording || voice.speaking || working || (generatedMedia?.playingID != nil && generatedMedia?.paused == false), level: max(voice.meter.level, generatedMedia?.level ?? 0), working: working, listening: voice.recording)
            OrbTouchSurface(enabled: enabled, label: status, working: working, cancelOnTouchDown: voice.inputPending || working, onTap: onTap, onCancel: working ? onStop : onCancel)
                .frame(width: 84, height: 80)
        }.frame(width: 84, height: 80)
            .overlay(alignment: .top) {
                if voice.recording {
                    Text("Listening").font(.caption2).foregroundStyle(PhoneTheme.secondary)
                        .fixedSize().offset(y: -14).allowsHitTesting(false)
                }
            }
    }
}
