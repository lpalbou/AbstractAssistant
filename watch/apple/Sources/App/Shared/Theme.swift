import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
}

/// Palette from the design mockups (untracked/watch/design/screens).
enum Theme {
    static let ground = Color(hex: 0x0a0a12)
    static let card = Color(hex: 0x15151f)
    static let line = Color(hex: 0x2a2a3a)
    static let text = Color(hex: 0xeceef5)
    static let text2 = Color(hex: 0xc4c6d4)
    static let muted = Color(hex: 0x8f91a6)
    static let indigo = Color(hex: 0x818cf8)
    static let indigoButton = Color(hex: 0x4f46e5)
    static let cyan = Color(hex: 0x22d3ee)
    static let green = Color(hex: 0x34d399)
    static let greenButton = Color(hex: 0x059669)
    static let amber = Color(hex: 0xfbbf24)
    static let red = Color(hex: 0xf87171)
    static let redButton = Color(hex: 0xb91c1c)
    static let neutralButton = Color(hex: 0x1c1c28)

    static func statusColor(_ status: String) -> Color {
        switch status {
        case "waiting": amber
        case "running": cyan
        case "completed", "done", "ok": green
        case "failed", "cancelled": red
        default: muted
        }
    }

    static func statusLabel(_ status: String) -> String { status == "completed" ? "done" : status }
}

/// A toolbar icon that stays readable: white glyph on a neutral glass tint (the app's indigo tint
/// otherwise colours both the button and its glyph).
struct BarIcon: View {
    let symbol: String
    var color: Color = Theme.text
    var body: some View { Image(systemName: symbol).foregroundStyle(color) }
}

extension Font {
    /// The system text styles (they follow the watch's text size, Dynamic Type), in the rounded design.
    static func rounded(_ style: Font.TextStyle, weight: Font.Weight = .regular) -> Font {
        .system(style, design: .rounded, weight: weight)
    }
    static func mono(_ style: Font.TextStyle, weight: Font.Weight = .regular) -> Font {
        .system(style, design: .monospaced, weight: weight)
    }
}

struct Card<Content: View>: View {
    var fill: Color = Theme.card
    var stroke: Color? = nil
    @ViewBuilder var content: Content
    var body: some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10).padding(.vertical, 8)
            .background(fill, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay {
                if let stroke { RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(stroke, lineWidth: 1) }
            }
    }
}

struct Pill: View {
    let text: String
    let color: Color
    var body: some View {
        Text(text).font(.rounded(.caption2, weight: .semibold)).lineLimit(1)
            .padding(.horizontal, 6).padding(.vertical, 2)
            .foregroundStyle(color)
            .overlay(Capsule().strokeBorder(color, lineWidth: 1))
            .fixedSize()
    }
}

struct StatusDot: View {
    let color: Color
    var body: some View {
        Circle().fill(color).frame(width: 8, height: 8)
            .padding(5).background(color.opacity(0.18), in: Circle())
    }
}

struct FilledButtonStyle: ButtonStyle {
    let fill: Color
    var foreground: Color = Theme.text
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.rounded(.body, weight: .semibold))
            .foregroundStyle(foreground)
            .frame(maxWidth: .infinity, minHeight: 40)
            .background(fill.opacity(configuration.isPressed ? 0.7 : 1), in: Capsule())
    }
}

struct Footnote: View {
    let text: String
    var mono = false
    var body: some View {
        Text(text).font(mono ? .mono(.caption2) : .rounded(.caption2)).foregroundStyle(Theme.muted)
            .multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.top, 4)
    }
}

extension View {
    /// Dark ground behind every screen.
    func screen(_ title: String) -> some View {
        self.navigationTitle(title)
            .toolbarTitleDisplayMode(.inline)
            .containerBackground(Theme.ground, for: .navigation)
    }
}
