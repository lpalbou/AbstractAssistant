import SwiftUI
import WatchKit

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

extension Color {
    /// "#rrggbb" (an entity's colour from the gateway); nil when malformed.
    init?(hexString: String) {
        var s = Substring(hexString.trimmingCharacters(in: .whitespaces))
        if s.hasPrefix("#") { s = s.dropFirst() }
        guard s.count == 6, s.allSatisfy(\.isHexDigit), let v = UInt32(s, radix: 16) else { return nil }
        self.init(hex: v)
    }
}

/// The layout rule for screens with actions: content from the top, actions pinned to the bottom
/// when everything fits on one screen (a Spacer before the actions does it); a longer screen
/// scrolls as usual, the actions after the content.
struct FitScroll<Content: View>: View {
    @ViewBuilder let content: () -> Content
    var body: some View {
        GeometryReader { geo in
            ScrollView {
                content().frame(maxWidth: .infinity, minHeight: geo.size.height, alignment: .top)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
    }
}

/// The orb's stage: as tall as what is left of the screen below the scroll view's top (`top`: where
/// the visible area starts on screen, which no scroll moves), with its content (drawn in a
/// screen-sized box) centred on the screen itself, whatever the bars above take on this watch. The
/// same on every visit: it is never measured from the stage itself, whose place changes with the
/// scroll (a page reopened scrolled down used to keep a wrong top). Each orb design keeps what it
/// draws clear of the top row.
struct ScreenCentered<Content: View, Bottom: View>: View {
    let width: CGFloat
    let top: CGFloat
    @ViewBuilder let content: (CGFloat) -> Content
    @ViewBuilder let bottom: () -> Bottom

    var body: some View {
        let screen = WKInterfaceDevice.current().screenBounds.size
        let t = max(0, top)
        ZStack(alignment: .bottom) {
            content(min(width, screen.height))
                .frame(width: width, height: screen.height)
                .position(x: width / 2, y: screen.height / 2 - t)
            bottom()
        }
        .frame(width: width, height: max(0, screen.height - t))
    }
}

/// Shares a text or a link from the watch through the system share sheet (Messages, Mail, …), as a
/// round icon like Back. watchOS has no clipboard (`UIPasteboard` is unavailable there), so sending
/// it on is how a text leaves the watch. Any `Transferable` item: a `URL`, a `String`.
struct ShareIcon<Item: Transferable>: View {
    let item: Item
    var subject: String?
    var body: some View {
        ShareLink(item: item, subject: subject.map { Text($0) }, preview: SharePreview(subject ?? "AbstractAssistant")) {
            GlassIcon(symbol: "square.and.arrow.up").rowReach()
        }
            .buttonStyle(GlassPress())
            .accessibilityLabel("Share")
    }
}

extension View {
    /// The touch area of an icon in the top row reaches `RowReach.vertical` above and below its
    /// circle (and `trailing` to its right): a fingertip is wider than the 35 pt drawn. A real frame,
    /// not a negative padding, which a watch does not hit-test beyond.
    func rowReach(trailing: CGFloat = 0) -> some View {
        padding(.vertical, RowReach.vertical).padding(.trailing, trailing).contentShape(Rectangle())
    }

    /// A control on the top line, right beside the corner button (Back). The system bar is hidden on
    /// every screen and the row is drawn here, where the bar's was: the corner button itself is drawn
    /// once, by the app, over every page, so it never moves from page to page; a control drawn over
    /// the bar is not tappable on a real watch (the bar takes the touch). The edge swipe still goes
    /// back; the time stays. This IS the page's screen: never add `.screen` beside it (two rows would
    /// each take a band, and the page and the control would start a band lower).
    func besideBack<V: View>(@ViewBuilder _ control: () -> V) -> some View {
        modifier(TopRow(title: nil, control: control(), systemBar: false))
    }
}

/// Every screen's top row: the page's title centred between the corner button and the time, the
/// page starting just below the row, a fade under it. `systemBar`: the system's own bar instead (the
/// first-launch choice, before the app's corner button exists).
private struct TopRow<V: View>: ViewModifier {
    let title: String?
    let control: V
    let systemBar: Bool
    /// Set by a row for its page: a page is one row (`.screen` or `.besideBack`), never both — each
    /// row takes its own band, and a second would start the page and its control a band lower.
    @Environment(\.insideTopRow) private var nested
    @ViewBuilder func body(content: Content) -> some View {
        if nested {
            let _ = assertionFailure("a page has two top rows (.screen and .besideBack): use one")
            content
        } else if systemBar {
            content.navigationTitle(title ?? "").toolbarTitleDisplayMode(.inline).containerBackground(Theme.ground, for: .navigation)
        } else {
            // The page starts below the row's band and is cut there: nothing is ever drawn behind the
            // corner button, the title or the time, at first or scrolled (the band is the screen's
            // own, not a bar laid over the page).
            GeometryReader { screen in
                VStack(spacing: 0) {
                    Color.clear.frame(height: CornerButton.band)
                    content.frame(width: screen.size.width, height: max(0, screen.size.height - CornerButton.band), alignment: .top)
                        .clipped()
                        .environment(\.insideTopRow, true)
                }
            }
            .ignoresSafeArea()
            .background(Theme.ground.ignoresSafeArea())
            .navigationTitle(title ?? "")
            .toolbar(.hidden, for: .navigationBar)
            .containerBackground(Theme.ground, for: .navigation)
            // The row's band takes any tap on it, as the system bar did: what is scrolled beneath it
            // is read, not tapped (a row comes out from under it with a scroll).
            .overlay(alignment: .top) {
                Color.clear.frame(height: CornerButton.band).contentShape(Rectangle()).onTapGesture {}.ignoresSafeArea()
            }
            .overlay(alignment: .top) {
                if let title, !title.isEmpty {
                    Text(title)
                        .font(.system(.body, design: .rounded, weight: .semibold)).foregroundStyle(Theme.text)
                        .lineLimit(1).minimumScaleFactor(0.7)
                        // Centred between the corner button and the time, which shares the line (the
                        // time's digits take up to ~50 pt at the right, "18:01").
                        .frame(maxWidth: .infinity)
                        .padding(.leading, CornerButton.leading + CornerButton.size + 4).padding(.trailing, CornerButton.timeWidth + 6)
                        .frame(height: CornerButton.size).padding(.top, CornerButton.top)
                        .allowsHitTesting(false)
                        .ignoresSafeArea()
                        .accessibilityIdentifier("screen.title")
                }
            }
            .overlay(alignment: .topLeading) {
                HStack(spacing: 6) {
                    Color.clear.frame(width: CornerButton.size, height: CornerButton.size).rowReach()   // the corner button's place
                    control
                }
                // The row owns its band, whatever is scrolled beneath: a tap just beside an icon
                // lands here and does nothing (it never reaches the orb, which would start listening).
                // The circles sit on the time's line (`CornerButton.top`).
                .padding(EdgeInsets(top: 0, leading: 6, bottom: 14 - RowReach.vertical, trailing: 6))
                .background(Color.clear.contentShape(Rectangle()).onTapGesture {})
                .padding(.leading, CornerButton.leading - 6).padding(.top, CornerButton.top - RowReach.vertical)
                .ignoresSafeArea()
            }
        }
    }
}

private struct InsideTopRowKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    /// True under a page's top row: a second row there is a mistake (see `TopRow`).
    var insideTopRow: Bool { get { self[InsideTopRowKey.self] } set { self[InsideTopRowKey.self] = newValue } }
}

/// The one button at the top left of every page, drawn by the app over the pages so it never moves:
/// the gear on Home (Settings), Back everywhere else, morphing from one to the other.
struct CornerButton: View {
    /// `top`: the circle's top, 8 pt down, so that its centre (25.5 pt) is the system time's (the
    /// time's digits run from 20 to 31 pt on a 46 mm; measured on a screenshot): Back, the title and
    /// the icons beside Back sit on the time's line.
    static let size: CGFloat = 35, leading: CGFloat = 15, top: CGFloat = 8
    /// The top row's band, from the screen's top: the page starts below it (5 pt under the circles).
    static let band: CGFloat = top + size + 5
    /// The room the system time takes at the right of the row ("18:01", with its margin).
    static let timeWidth: CGFloat = 58
    @EnvironmentObject private var model: AppModel
    var body: some View {
        let home = model.atHome
        Button { if home { model.openSettings() } else { model.goBack() } } label: {
            GlassIcon(symbol: home ? "gearshape" : "chevron.left")
                .contentTransition(.symbolEffect(.replace))
                .rowReach()
        }
        .buttonStyle(GlassPress())
        .accessibilityLabel(home ? "Settings" : "Back")
        .animation(.easeInOut(duration: 0.25), value: home)
        .padding(.leading, Self.leading).padding(.top, Self.top - RowReach.vertical)
        .ignoresSafeArea()
    }
}

enum RowReach { static let vertical: CGFloat = 9 }

/// A button that fires on a tap only: a finger that moves (a swipe across a full-width row) is not
/// a tap, whatever the order in which the watch reports the swipe and the lift (the plain style
/// fires wherever the finger lifts on the button).
struct TapButtonStyle: PrimitiveButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(enabled ? 1 : 0.5)                      // dimmed while it cannot be used
            .onTapGesture { if enabled { configuration.trigger() } }
    }
}

extension PrimitiveButtonStyle where Self == TapButtonStyle {
    static var tap: TapButtonStyle { TapButtonStyle() }
}

/// The press of a round icon: it dips and dims while held, so a tap visibly lands.
struct GlassPress: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.86 : 1)
            .opacity(configuration.isPressed ? 0.7 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// A round button face like the system's Back button (same size, same fill): the discreet
/// secondary controls (keyboard, ✕, read aloud, rewind, edit, run now).
struct GlassIcon: View {
    let symbol: String
    var size: CGFloat = 35
    /// The glyphs drawn in a round icon (measured by `--render-icons`).
    /// A glyph's optical centring in its circle: SF Symbols centre their bounding box, and a glyph
    /// whose weight sits off it (the share box below its arrow, a chevron's point) looks off by a
    /// point or two. Measured with `--render-icons` (in points for a 35 pt circle).
    static func optical(_ symbol: String, size: CGFloat = 35) -> CGSize {
        let k = size / 35
        switch symbol {
        case "square.and.arrow.up": return CGSize(width: 0, height: -1.0 * k)
        case "chevron.left": return CGSize(width: 0.85 * k, height: 0)
        case "speaker.wave.2.fill": return CGSize(width: 0.6 * k, height: 0)
        case "checkmark.shield.fill": return CGSize(width: 0, height: 0.3 * k)
        case "play.fill": return CGSize(width: 0.3 * k, height: 0)
        case "paperplane.fill": return CGSize(width: -0.4 * k, height: 0.4 * k)
        default: return .zero
        }
    }
    static let symbols = ["chevron.left", "square.and.arrow.up", "stop.fill", "play.fill", "pause.fill", "backward.fill",
                          "keyboard", "wrench.and.screwdriver", "pencil", "speaker.wave.2.fill", "checkmark.shield.fill", "paperplane.fill"]
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.45, weight: .semibold))
            .foregroundStyle(Theme.text)
            .offset(Self.optical(symbol, size: size))
            .frame(width: size, height: size)
            .background(Color(red: 28 / 255, green: 28 / 255, blue: 38 / 255), in: Circle())   // the Back button's fill
            .overlay(Circle().strokeBorder(Color.white.opacity(0.12), lineWidth: 0.5))
            .contentShape(Circle())
    }
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

/// What you have not seen yet: its number in an orange ring (an automation's runs since you last
/// looked at it).
struct CountBadge: View {
    let count: Int
    var color: Color = Theme.amber
    var body: some View {
        Text("\(count)").font(.rounded(.caption2, weight: .bold)).monospacedDigit().foregroundStyle(color)
            .frame(minWidth: 24, minHeight: 24).padding(.horizontal, count > 9 ? 4 : 0)
            .background(color.opacity(0.16), in: Capsule())
            .overlay(Capsule().strokeBorder(color, lineWidth: 1.5))
            .fixedSize()
            .accessibilityLabel(count == 1 ? "1 new run" : "\(count) new runs")
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
    var font: Font = .rounded(.body, weight: .semibold)
    var lines = 1
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(font).lineLimit(lines).minimumScaleFactor(0.75)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 12).padding(.vertical, 4)
            .foregroundStyle(foreground)
            .frame(maxWidth: .infinity, minHeight: 40)
            .background(fill.opacity(configuration.isPressed ? 0.7 : 1), in: Capsule())
            .modifier(DimWhenDisabled())
    }
}

private struct DimWhenDisabled: ViewModifier {
    @Environment(\.isEnabled) private var enabled
    func body(content: Content) -> some View { content.opacity(enabled ? 1 : 0.45) }
}

extension View {
    /// A screen: dark ground, its title in the top row beside the corner button (`systemBar`: the
    /// system's own bar, for the first-launch choice).
    func screen(_ title: String, systemBar: Bool = false) -> some View {
        modifier(TopRow(title: title, control: EmptyView(), systemBar: systemBar))
    }
}


/// "Loading" with three dots that fill in turn: what a line says until its information is in.
struct LoadingText: View {
    var text = "Loading"
    @Environment(\.isLuminanceReduced) private var dimmed
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        TimelineView(.animation(minimumInterval: 0.4, paused: dimmed || scenePhase != .active)) { ctx in
            let n = Int(ctx.date.timeIntervalSinceReferenceDate / 0.4) % 4
            HStack(spacing: 0) {
                Text(text)
                ForEach(0..<3, id: \.self) { i in Text(".").opacity(i < n ? 1 : 0) }   // the width never moves
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(text)
    }
}

#if DEBUG
/// Hooks only UI tests use (a 4 Hz readout of the voice's position): on only when a test launched
/// the app (every test passes --no-notification-prompt; a deploy or a tap on the watch does not),
/// so the build on the wrist never pays for them.
enum UITestHooks {
    static let on = ProcessInfo.processInfo.arguments.contains("--no-notification-prompt")
}
#endif
