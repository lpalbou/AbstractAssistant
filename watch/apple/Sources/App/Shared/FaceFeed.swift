import AbstractGatewayClient
import SwiftUI
import WidgetKit

/// The watch face's view of the gateway: what the app (or its background check) has just read.
extension FaceSnapshot {
    /// The approvals and questions waiting for you.
    static func waits(_ waits: [Wait]) {
        update { $0.needYou = waits.count; $0.firstNeed = waits.first?.headline }
    }

    /// The next active automation to run, and the results not seen yet.
    static func automations(_ list: [AutomationSummary], now: Date = Date()) {
        let next = list.filter { $0.status == "active" }
            .compactMap { a in a.nextFireAt.flatMap(ISO8601.date).map { (name: a.name ?? "Automation", at: $0) } }
            .filter { $0.at > now }
            .min { $0.at < $1.at }
        update {
            $0.nextName = next?.name; $0.nextAt = next?.at
            $0.newResults = list.reduce(0) { $0 + ($1.attention?.unseenCount ?? 0) }
        }
    }
}

extension FaceSnapshot {
    @MainActor private static var reloaded = false

    /// Draws your avatar for the watch face: the orb style chosen, as on Home, in each of the face's
    /// states (at rest; speaking, for news; listening, for what needs you); once per style (the
    /// face keeps the pictures until the style changes). Two pictures per state: in colour, and
    /// its light as transparency for a face that draws its complications in one tint.
    @MainActor static func drawAvatar(_ design: OrbDesign) {
        let id = "\(design.rawValue)#5"
        let missing = FaceState.allCases.contains { avatar($0) == nil || avatar($0, mask: true) == nil }
        guard avatarId != id || missing else {
            // Nothing to draw again: still, once per launch, the face draws the complication afresh
            // (an app updated under it keeps showing the last picture until then).
            if !reloaded { reloaded = true; WidgetCenter.shared.reloadTimelines(ofKind: kind) }
            return
        }
        func voice(_ level: Double, _ low: Double, _ high: Double) -> VoiceFeatures {
            VoiceFeatures(level: level, bands: (0..<VoiceFeatures.bandCount).map { i in
                level * (low * exp(-pow(Double(i) - 1.5, 2) / 1.5) + high * exp(-pow(Double(i) - 5.5, 2) / 1.5)) })
        }
        var drawn: [FaceState: (color: Data, mask: Data)] = [:]
        for state in FaceState.allCases {
            // (the voice, engaged, speaking, the frame's time), as the design sheets render them
            let (v, engaged, speaking, t): (VoiceFeatures, Bool, Bool, Double) = switch state {
            case .rest: (.silent, false, false, 812_345_678.0)
            case .news: (voice(0.8, 1, 0.5), true, true, 1000.3)
            case .needYou: (voice(0.7, 0.8, 0.6), true, false, 1001.2)
            }
            let engine = OrbEngine()
            for k in 0..<45 { engine.step(t: t - 1.5 + Double(k) / 30, voice: v, engaged: engaged, thinking: false, speaking: speaking) }
            let art = OrbCanvas(t: t, engine: engine, design: design, look: .assistant)
                .frame(width: 120, height: 120)
            let renderer = ImageRenderer(content: art)
            renderer.scale = 2
            guard let image = renderer.cgImage, let p = pictures(image) else {
                #if DEBUG
                print("face avatar: \(design.name) \(state.rawValue) not drawn (image \(renderer.cgImage == nil ? "nil" : "ok"))")
                #endif
                return
            }
            drawn[state] = p
        }
        setAvatar(drawn, id: id)
        #if DEBUG
        print("face avatar: \(design.name) drawn in \(drawn.count) states, kept: \(avatar() != nil)")
        #endif
    }

    /// The drawing without the empty margin round it (each style fills a different share of its
    /// box): the smallest square, centred where the drawing is, that holds every visible pixel.
    /// And the same, its light (how bright each pixel is) as transparency, white: a face in one
    /// tint draws it as a mask in its accent, so the orb keeps its shape and texture there.
    private static func pictures(_ image: CGImage) -> (color: Data, mask: Data)? {
        let w = image.width, h = image.height
        let space = CGColorSpaceCreateDeviceRGB()
        let info = CGImageAlphaInfo.premultipliedLast.rawValue
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &pixels, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: space, bitmapInfo: info) else { return nil }
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        var minX = w, minY = h, maxX = -1, maxY = -1
        for y in 0..<h { for x in 0..<w where pixels[(y * w + x) * 4 + 3] > 24 {
            minX = min(minX, x); maxX = max(maxX, x); minY = min(minY, y); maxY = max(maxY, y)
        } }
        guard maxX > minX, maxY > minY else { return nil }
        let side = max(maxX - minX, maxY - minY) + 4
        let cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
        let rect = CGRect(x: cx - side / 2, y: cy - side / 2, width: side, height: side)
            .intersection(CGRect(x: 0, y: 0, width: w, height: h))
        // The light as alpha (premultiplied white: every channel the same), stretched so the
        // brightest point of the style is opaque (a dark scene such as the sea at night would be
        // faint otherwise) and lifted, so the faint points of a resting orb still show at a
        // complication's size; a face in one tint has only its accent and this transparency.
        var brightest: UInt8 = 1
        for i in stride(from: 0, to: pixels.count, by: 4) { brightest = max(brightest, pixels[i], pixels[i + 1], pixels[i + 2]) }
        var light = [UInt8](repeating: 0, count: w * h * 4)
        for i in stride(from: 0, to: pixels.count, by: 4) {
            let b = Double(max(pixels[i], pixels[i + 1], pixels[i + 2])) / Double(brightest)
            let v = UInt8((255 * pow(min(1, b), 0.55)).rounded())
            light[i] = v; light[i + 1] = v; light[i + 2] = v; light[i + 3] = v
        }
        guard let maskCtx = CGContext(data: &light, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: space, bitmapInfo: info),
              let maskImage = maskCtx.makeImage(),
              let color = image.cropping(to: rect), let mask = maskImage.cropping(to: rect),
              let colorData = UIImage(cgImage: color).pngData(), let maskData = UIImage(cgImage: mask).pngData() else { return nil }
        return (colorData, maskData)
    }
}
