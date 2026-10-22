import AbstractGatewayClient
import SwiftUI

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
    /// Draws your avatar for the watch face: the orb style chosen, at rest, as on Home; once per
    /// style (the face keeps the picture until the style changes).
    @MainActor static func drawAvatar(_ design: OrbDesign) {
        let id = "\(design.rawValue)#2"
        guard avatarId != id else { return }
        let art = OrbCanvas(t: 812_345_678.0, engine: OrbEngine(), design: design, look: .assistant)
            .frame(width: 120, height: 120)
        let renderer = ImageRenderer(content: art)
        renderer.scale = 2
        guard let image = renderer.cgImage, let png = UIImage(cgImage: trimmed(image)).pngData() else { return }
        setAvatar(png, id: id)
    }

    /// The drawing without the empty margin round it (each style fills a different share of its
    /// box): the smallest square, centred where the drawing is, that holds every visible pixel.
    private static func trimmed(_ image: CGImage) -> CGImage {
        let w = image.width, h = image.height
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &pixels, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return image }
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        var minX = w, minY = h, maxX = -1, maxY = -1
        for y in 0..<h { for x in 0..<w where pixels[(y * w + x) * 4 + 3] > 24 {
            minX = min(minX, x); maxX = max(maxX, x); minY = min(minY, y); maxY = max(maxY, y)
        } }
        guard maxX > minX, maxY > minY else { return image }
        let side = max(maxX - minX, maxY - minY) + 4
        let cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
        let rect = CGRect(x: cx - side / 2, y: cy - side / 2, width: side, height: side)
            .intersection(CGRect(x: 0, y: 0, width: w, height: h))
        return image.cropping(to: rect) ?? image
    }
}
