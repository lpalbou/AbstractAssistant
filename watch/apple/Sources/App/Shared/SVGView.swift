import AbstractGatewayClient
import SwiftUI

/// An SVG drawing drawn natively (watchOS has no web view): fitted into its frame, its aspect kept.
struct SVGView: View {
    let document: SVGDocument

    var body: some View {
        let box = document.viewBox
        Canvas { gc, size in SVGRenderer.draw(document, in: &gc, size: size) }
            .aspectRatio(box.width / max(1, box.height), contentMode: .fit)
            .accessibilityLabel("Drawing")
            .accessibilityIdentifier("svg.drawing")
    }
}

/// Draws an `SVGDocument` into a Canvas: each shape and text with its transform, paint, stroke,
/// opacity and effects (a blur or a drop shadow); gradients in the shape's bounding box or in user
/// space, as the drawing says.
enum SVGRenderer {
    static func draw(_ d: SVGDocument, in gc: inout GraphicsContext, size: CGSize) {
        let box = d.viewBox
        guard box.width > 0, box.height > 0 else { return }
        let scale = min(size.width / box.width, size.height / box.height)
        let fit = CGAffineTransform(translationX: (size.width - box.width * scale) / 2, y: (size.height - box.height * scale) / 2)
            .scaledBy(x: scale, y: scale).translatedBy(x: -box.minX, y: -box.minY)
        for node in d.nodes {
            let m = node.transform.concatenating(fit)
            let unit = abs(m.a * m.d - m.b * m.c).squareRoot()            // the node's scale on screen
            if node.effects.isEmpty {
                var g = gc
                g.opacity = node.style.opacity
                g.concatenate(m)
                drawNode(node, in: &g)
            } else {
                gc.drawLayer { layer in
                    layer.opacity = node.style.opacity
                    for e in node.effects {
                        switch e {
                        case .blur(let r): layer.addFilter(.blur(radius: r * unit))
                        case .shadow(let dx, let dy, let r, let c):
                            layer.addFilter(.shadow(color: color(c), radius: r * unit, x: dx * unit, y: dy * unit))
                        }
                    }
                    layer.concatenate(m)
                    drawNode(node, in: &layer)
                }
            }
        }
    }

    private static func drawNode(_ node: SVGNode, in g: inout GraphicsContext) {
        let s = node.style
        switch node.kind {
        case .shape(let cg):
            let path = Path(cg), box = cg.boundingBoxOfPath
            if let fill = s.fill {
                g.fill(path, with: shading(fill, box: box, alpha: s.fillOpacity), style: FillStyle(eoFill: s.evenOdd))
            }
            if let stroke = s.stroke, s.strokeWidth > 0 {
                g.stroke(path, with: shading(stroke, box: box, alpha: s.strokeOpacity),
                         style: StrokeStyle(lineWidth: s.strokeWidth, lineCap: s.lineCap, lineJoin: s.lineJoin,
                                            miterLimit: s.miterLimit, dash: s.dash.map { CGFloat($0) }))
            }
        case .text(let words, let at):
            guard let fill = s.fill else { return }
            let tint: Color = switch fill {
            case .color(let c): color(c, alpha: s.fillOpacity)
            case .gradient(let gr): gr.stops.first.map { color($0.color, alpha: s.fillOpacity) } ?? .black
            }
            let text = Text(words)
                .font(.system(size: s.fontSize, weight: weight(s.fontWeight), design: design(s.fontFamily)))
                .kerning(s.letterSpacing)
                .foregroundStyle(tint)
            let resolved = g.resolve(text)
            let size = resolved.measure(in: CGSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude))
            let baseline = resolved.firstBaseline(in: size)
            let shift: CGFloat = s.anchor == "middle" ? 0.5 : s.anchor == "end" ? 1 : 0
            g.draw(resolved, in: CGRect(x: at.x - shift * size.width, y: at.y - baseline, width: size.width, height: size.height))
        }
    }

    private static func shading(_ p: SVGPaint, box: CGRect, alpha: Double) -> GraphicsContext.Shading {
        switch p {
        case .color(let c): return .color(color(c, alpha: alpha))
        case .gradient(let gr):
            let stops = gr.stops.map { Gradient.Stop(color: color($0.color, alpha: alpha), location: $0.offset) }
            /// A gradient coordinate in the shape's units: its own, or a fraction of its bounding box.
            func point(_ x: Double, _ y: Double) -> CGPoint {
                let p = CGPoint(x: x, y: y).applying(gr.transform)
                return gr.userSpace ? p : CGPoint(x: box.minX + p.x * box.width, y: box.minY + p.y * box.height)
            }
            switch gr.kind {
            case .linear(let x1, let y1, let x2, let y2):
                return .linearGradient(Gradient(stops: stops), startPoint: point(x1, y1), endPoint: point(x2, y2))
            case .radial(let cx, let cy, let r):
                let radius = gr.userSpace ? r : r * (box.width + box.height) / 2
                return .radialGradient(Gradient(stops: stops), center: point(cx, cy), startRadius: 0, endRadius: radius)
            }
        }
    }

    private static func color(_ c: SVGColor, alpha: Double = 1) -> Color {
        Color(.sRGB, red: c.r, green: c.g, blue: c.b, opacity: c.a * alpha)
    }

    private static func weight(_ w: Int) -> Font.Weight {
        switch w {
        case ..<250: .thin
        case ..<350: .light
        case ..<450: .regular
        case ..<550: .medium
        case ..<650: .semibold
        case ..<750: .bold
        default: .heavy
        }
    }

    private static func design(_ family: String) -> Font.Design {
        let f = family.lowercased()
        if f.contains("mono") || f.contains("courier") { return .monospaced }
        if f.contains("serif") && !f.contains("sans") { return .serif }
        return .default
    }
}
