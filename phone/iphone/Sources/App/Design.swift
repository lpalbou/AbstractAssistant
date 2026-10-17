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

/// A small native drawing: no downloaded media, shader or continuously running render loop.
struct AssistantOrb: View {
    var size: CGFloat = 170
    var active = false
    var level: Double = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotate = false
    var body: some View {
        ZStack {
            Circle().fill(PhoneTheme.lavender.opacity(0.10)).blur(radius: size * 0.15).padding(-size * 0.08)
            Circle().fill(RadialGradient(colors: [.white.opacity(0.18), PhoneTheme.lavender.opacity(0.16), PhoneTheme.ground], center: .init(x: 0.28, y: 0.2), startRadius: 2, endRadius: size * 0.68))
            ForEach(0..<5) { index in
                Ellipse().stroke(AngularGradient(colors: [.clear, PhoneTheme.mint.opacity(0.7), PhoneTheme.lavender, .white.opacity(0.85), .clear], center: .center), lineWidth: index == 2 ? 1.6 : 0.7)
                    .frame(width: size * (0.65 + Double(index) * 0.07), height: size * 0.49)
                    .rotationEffect(.degrees(Double(index) * 34 + (rotate ? 110 : -15)))
            }
            Circle().stroke(.white.opacity(0.13), lineWidth: 0.8)
            Circle().fill(.white).frame(width: 5, height: 5).offset(x: size * 0.29, y: -size * 0.30).shadow(color: PhoneTheme.mint, radius: 6)
        }
        .frame(width: size, height: size)
        .scaleEffect(reduceMotion ? 1 : 1 + level * 0.18)
        .shadow(color: PhoneTheme.mint.opacity(level * 0.65), radius: 8 + level * 28)
        .animation(reduceMotion ? nil : .easeOut(duration: 0.06), value: level)
        .animation(reduceMotion ? nil : .easeInOut(duration: active ? 3 : 10).repeatForever(autoreverses: true), value: rotate)
        .onAppear { rotate = true }
        .accessibilityHidden(true)
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


/// Audio observations stay inside this small view, separate from the conversation list.
struct VoicePresence: View {
    let voice: VoiceController
    var working: Bool
    var compact: Bool
    var action: () -> Void
    private var status: String {
        if voice.recording { return "Listening" }
        if voice.transcribing { return "Transcribing" }
        if voice.speaking { return voice.paused ? "Reading paused" : "Reading aloud" }
        return working ? "Thinking" : "Tap to speak"
    }
    var body: some View {
        Button(action: action) {
            VStack(spacing: 10) {
                AssistantOrb(size: compact ? 68 : 170, active: voice.recording || voice.speaking || working, level: voice.meter.level)
                Text(status).font(.caption).foregroundStyle(PhoneTheme.secondary)
            }.frame(maxWidth: .infinity).padding(.vertical, compact ? 4 : 18)
        }.buttonStyle(.plain).accessibilityLabel(status).accessibilityHint(voice.speaking ? "Pause or resume reading" : "Record a voice message")
    }
}
