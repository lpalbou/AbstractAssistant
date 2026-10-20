import CoreGraphics
import Foundation

/// An SVG drawing read into what the watch can draw (watchOS has no web view): its view box and its
/// shapes and texts in document order, each with the transform to the view box, its resolved style
/// (inherited from its groups) and its effects. Covers what drawings made by an agent use: rect,
/// circle, ellipse, line, polyline, polygon, path (every command, arcs included), text, groups with
/// transforms and opacity, linear and radial gradients, dashes, and blur and drop-shadow filters.
/// Not drawn: embedded images, `use`, masks, clip paths, patterns, CSS stylesheets.
public struct SVGDocument: @unchecked Sendable {
    public var viewBox: CGRect
    public var nodes: [SVGNode]

    public enum ParseError: Error { case notSVG, unreadable }

    public static func parse(_ data: Data) throws -> SVGDocument {
        let tree = SVGTree()
        let parser = XMLParser(data: data)
        parser.delegate = tree
        parser.shouldProcessNamespaces = true
        guard parser.parse(), let root = tree.root else { throw ParseError.unreadable }
        guard root.name == "svg" else { throw ParseError.notSVG }
        return SVGBuilder(root: root).build()
    }
}

public struct SVGNode: @unchecked Sendable {
    public enum Kind { case shape(CGPath), text(String, CGPoint) }
    public var kind: Kind
    /// From the element's own units to the view box.
    public var transform: CGAffineTransform
    public var style: SVGStyle
    public var effects: [SVGEffect]
}

public struct SVGColor: Hashable, Sendable {
    public var r: Double, g: Double, b: Double, a: Double
    public init(r: Double, g: Double, b: Double, a: Double = 1) { self.r = r; self.g = g; self.b = b; self.a = a }
    public static let black = SVGColor(r: 0, g: 0, b: 0)
}

public struct SVGGradient: @unchecked Sendable {
    public enum Kind { case linear(x1: Double, y1: Double, x2: Double, y2: Double), radial(cx: Double, cy: Double, r: Double) }
    public struct Stop: Sendable { public var offset: Double; public var color: SVGColor }
    public var kind: Kind
    public var stops: [Stop]
    /// Coordinates in the shape's own units; false: fractions of its bounding box (the default).
    public var userSpace: Bool
    public var transform: CGAffineTransform
}

public enum SVGPaint: @unchecked Sendable {
    case color(SVGColor)
    case gradient(SVGGradient)
}

public enum SVGEffect: Sendable {
    case blur(radius: Double)
    case shadow(dx: Double, dy: Double, radius: Double, color: SVGColor)
}

public struct SVGStyle: @unchecked Sendable {
    public var fill: SVGPaint? = .color(.black)
    public var stroke: SVGPaint? = nil
    public var strokeWidth = 1.0
    public var fillOpacity = 1.0, strokeOpacity = 1.0
    /// The element's opacity times its groups'.
    public var opacity = 1.0
    public var lineCap: CGLineCap = .butt
    public var lineJoin: CGLineJoin = .miter
    public var miterLimit = 4.0
    public var dash: [Double] = []
    public var evenOdd = false
    public var fontSize = 16.0
    public var fontWeight = 400
    public var fontFamily = ""
    /// start, middle or end.
    public var anchor = "start"
    public var letterSpacing = 0.0
    public var color = SVGColor.black
}

// MARK: - The XML tree

final class SVGElement {
    let name: String
    let attributes: [String: String]
    var children: [SVGElement] = []
    var text = ""
    init(name: String, attributes: [String: String]) { self.name = name; self.attributes = attributes }
}

private final class SVGTree: NSObject, XMLParserDelegate {
    var root: SVGElement?
    private var stack: [SVGElement] = []
    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName: String?,
                attributes: [String: String] = [:]) {
        let e = SVGElement(name: elementName, attributes: attributes)
        if let parent = stack.last { parent.children.append(e) } else { root = e }
        stack.append(e)
    }
    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName: String?) {
        stack.removeLast()
    }
    func parser(_ parser: XMLParser, foundCharacters string: String) {
        // A text's words, its tspans' included.
        for e in stack.reversed() where e.name == "text" { e.text += string; break }
    }
}

// MARK: - From the tree to what is drawn

private struct SVGBuilder {
    let root: SVGElement
    var ids: [String: SVGElement] = [:]

    init(root: SVGElement) {
        self.root = root
        func index(_ e: SVGElement) {
            if let id = e.attributes["id"] { ids[id] = e }
            e.children.forEach(index)
        }
        index(root)
    }

    func build() -> SVGDocument {
        let a = root.attributes
        let box: CGRect
        let vb = SVGNumbers.list(a["viewBox"] ?? "")
        if vb.count == 4, vb[2] > 0, vb[3] > 0 {
            box = CGRect(x: vb[0], y: vb[1], width: vb[2], height: vb[3])
        } else {
            box = CGRect(x: 0, y: 0, width: SVGNumbers.length(a["width"]) ?? 300, height: SVGNumbers.length(a["height"]) ?? 150)
        }
        var nodes: [SVGNode] = []
        walk(root, style: SVGStyle(), transform: .identity, effects: [], into: &nodes)
        return SVGDocument(viewBox: box, nodes: nodes)
    }

    private static let skipped: Set<String> = ["defs", "linearGradient", "radialGradient", "filter", "clipPath", "mask", "pattern",
                                               "symbol", "style", "title", "desc", "metadata", "marker", "script"]

    private func walk(_ e: SVGElement, style parent: SVGStyle, transform: CGAffineTransform, effects: [SVGEffect], into nodes: inout [SVGNode]) {
        guard !Self.skipped.contains(e.name) else { return }
        let attrs = merged(e)
        if attrs["display"] == "none" || attrs["visibility"] == "hidden" { return }
        var style = parent
        apply(attrs, to: &style)
        style.opacity = parent.opacity * (SVGNumbers.number(attrs["opacity"]) ?? 1)
        let t = SVGTransform.parse(attrs["transform"] ?? "").concatenating(transform)
        var fx = effects
        if let f = attrs["filter"], let id = SVGNumbers.url(f), let filter = ids[id] { fx += self.effects(of: filter) }
        switch e.name {
        case "svg", "g", "a", "switch":
            for c in e.children { walk(c, style: style, transform: t, effects: fx, into: &nodes) }
        case "text":
            let x = SVGNumbers.list(attrs["x"] ?? "").first ?? 0, y = SVGNumbers.list(attrs["y"] ?? "").first ?? 0
            let words = e.text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            if !words.isEmpty { nodes.append(SVGNode(kind: .text(words, CGPoint(x: x, y: y)), transform: t, style: style, effects: fx)) }
        default:
            if let path = shape(e.name, attrs) { nodes.append(SVGNode(kind: .shape(path), transform: t, style: style, effects: fx)) }
        }
    }

    /// The element's attributes with its `style` declarations over them.
    private func merged(_ e: SVGElement) -> [String: String] {
        var a = e.attributes
        for decl in (a["style"] ?? "").split(separator: ";") {
            let kv = decl.split(separator: ":", maxSplits: 1)
            guard kv.count == 2 else { continue }
            a[kv[0].trimmingCharacters(in: .whitespaces)] = kv[1].trimmingCharacters(in: .whitespaces)
        }
        return a
    }

    private func apply(_ a: [String: String], to s: inout SVGStyle) {
        if let c = a["color"], let color = SVGNumbers.color(c, current: s.color) { s.color = color }
        if let f = a["fill"] { s.fill = paint(f, current: s.color) }
        if let v = a["stroke"] { s.stroke = paint(v, current: s.color) }
        if let w = SVGNumbers.length(a["stroke-width"]) { s.strokeWidth = w }
        if let v = SVGNumbers.number(a["fill-opacity"]) { s.fillOpacity = v }
        if let v = SVGNumbers.number(a["stroke-opacity"]) { s.strokeOpacity = v }
        switch a["stroke-linecap"] { case "round": s.lineCap = .round; case "square": s.lineCap = .square; case "butt": s.lineCap = .butt; default: break }
        switch a["stroke-linejoin"] { case "round": s.lineJoin = .round; case "bevel": s.lineJoin = .bevel; case "miter": s.lineJoin = .miter; default: break }
        if let v = SVGNumbers.number(a["stroke-miterlimit"]) { s.miterLimit = v }
        if let d = a["stroke-dasharray"] { s.dash = d == "none" ? [] : SVGNumbers.list(d) }
        if let r = a["fill-rule"] { s.evenOdd = r == "evenodd" }
        if let v = SVGNumbers.length(a["font-size"]) { s.fontSize = v }
        if let w = a["font-weight"] { s.fontWeight = w == "bold" ? 700 : w == "normal" ? 400 : Int(w) ?? s.fontWeight }
        if let f = a["font-family"] { s.fontFamily = f }
        if let v = a["text-anchor"] { s.anchor = v }
        if let v = SVGNumbers.length(a["letter-spacing"]) { s.letterSpacing = v }
    }

    private func paint(_ v: String, current: SVGColor) -> SVGPaint? {
        if v == "none" || v == "transparent" { return nil }
        if let id = SVGNumbers.url(v) {
            if let g = gradient(id) { return .gradient(g) }
            // An unknown reference: its fallback colour, else nothing.
            let rest = v.split(separator: ")", maxSplits: 1).dropFirst().first.map { $0.trimmingCharacters(in: .whitespaces) } ?? ""
            return SVGNumbers.color(rest, current: current).map { .color($0) }
        }
        return SVGNumbers.color(v, current: current).map { .color($0) } ?? .color(.black)
    }

    /// A gradient, its stops and attributes inherited from the one it references (`href`).
    private func gradient(_ id: String, depth: Int = 0) -> SVGGradient? {
        guard depth < 8, let e = ids[id], e.name == "linearGradient" || e.name == "radialGradient" else { return nil }
        let base = (e.attributes["href"] ?? e.attributes["xlink:href"]).map { $0.hasPrefix("#") ? String($0.dropFirst()) : $0 }
            .flatMap { gradient($0, depth: depth + 1) }
        let a = e.attributes
        func coord(_ key: String, _ fallback: Double) -> Double { SVGNumbers.fraction(a[key]) ?? fallback }
        let kind: SVGGradient.Kind
        if e.name == "linearGradient" {
            if case .linear(let x1, let y1, let x2, let y2)? = base?.kind, a["x1"] == nil, a["x2"] == nil, a["y1"] == nil, a["y2"] == nil {
                kind = .linear(x1: x1, y1: y1, x2: x2, y2: y2)
            } else {
                kind = .linear(x1: coord("x1", 0), y1: coord("y1", 0), x2: coord("x2", 1), y2: coord("y2", 0))
            }
        } else {
            kind = .radial(cx: coord("cx", 0.5), cy: coord("cy", 0.5), r: coord("r", 0.5))
        }
        var stops: [SVGGradient.Stop] = []
        var last = 0.0
        for s in e.children where s.name == "stop" {
            let sa = merged(s)
            let offset = max(last, min(1, SVGNumbers.fraction(sa["offset"]) ?? 0))
            last = offset
            var c = SVGNumbers.color(sa["stop-color"] ?? "black", current: .black) ?? .black
            c.a *= SVGNumbers.number(sa["stop-opacity"]) ?? 1
            stops.append(.init(offset: offset, color: c))
        }
        if stops.isEmpty { stops = base?.stops ?? [] }
        guard !stops.isEmpty else { return nil }
        let units = a["gradientUnits"].map { $0 == "userSpaceOnUse" } ?? base?.userSpace ?? false
        let t = a["gradientTransform"].map(SVGTransform.parse) ?? base?.transform ?? .identity
        return SVGGradient(kind: kind, stops: stops, userSpace: units, transform: t)
    }

    private func effects(of filter: SVGElement) -> [SVGEffect] {
        filter.children.compactMap { p in
            let a = merged(p)
            switch p.name {
            case "feGaussianBlur":
                return .blur(radius: SVGNumbers.list(a["stdDeviation"] ?? "0").first ?? 0)
            case "feDropShadow":
                var c = SVGNumbers.color(a["flood-color"] ?? "black", current: .black) ?? .black
                c.a *= SVGNumbers.number(a["flood-opacity"]) ?? 1
                return .shadow(dx: SVGNumbers.number(a["dx"]) ?? 2, dy: SVGNumbers.number(a["dy"]) ?? 2,
                               radius: SVGNumbers.list(a["stdDeviation"] ?? "2").first ?? 2, color: c)
            default: return nil
            }
        }
    }

    private func shape(_ name: String, _ a: [String: String]) -> CGPath? {
        func n(_ k: String) -> Double { SVGNumbers.length(a[k]) ?? 0 }
        let p = CGMutablePath()
        switch name {
        case "rect":
            let w = n("width"), h = n("height")
            guard w > 0, h > 0 else { return nil }
            var rx = SVGNumbers.length(a["rx"]), ry = SVGNumbers.length(a["ry"])
            if rx == nil { rx = ry }; if ry == nil { ry = rx }
            let cw = min(rx ?? 0, w / 2), ch = min(ry ?? 0, h / 2)
            let r = CGRect(x: n("x"), y: n("y"), width: w, height: h)
            if cw > 0, ch > 0 { p.addRoundedRect(in: r, cornerWidth: cw, cornerHeight: ch) } else { p.addRect(r) }
        case "circle":
            let r = n("r"); guard r > 0 else { return nil }
            p.addEllipse(in: CGRect(x: n("cx") - r, y: n("cy") - r, width: 2 * r, height: 2 * r))
        case "ellipse":
            let rx = n("rx"), ry = n("ry"); guard rx > 0, ry > 0 else { return nil }
            p.addEllipse(in: CGRect(x: n("cx") - rx, y: n("cy") - ry, width: 2 * rx, height: 2 * ry))
        case "line":
            p.move(to: CGPoint(x: n("x1"), y: n("y1"))); p.addLine(to: CGPoint(x: n("x2"), y: n("y2")))
        case "polyline", "polygon":
            let v = SVGNumbers.list(a["points"] ?? "")
            guard v.count >= 4 else { return nil }
            p.move(to: CGPoint(x: v[0], y: v[1]))
            for i in stride(from: 2, to: v.count - 1, by: 2) { p.addLine(to: CGPoint(x: v[i], y: v[i + 1])) }
            if name == "polygon" { p.closeSubpath() }
        case "path":
            SVGPathData.append(a["d"] ?? "", to: p)
        default:
            return nil
        }
        return p.isEmpty ? nil : p
    }
}

// MARK: - Numbers, colours, transforms

enum SVGNumbers {
    /// The numbers in a list ("0 0 1600 1000", "10,20 30,40", "-42-24").
    static func list(_ s: String) -> [Double] {
        var scan = SVGScanner(s)
        var out: [Double] = []
        while let v = scan.number() { out.append(v) }
        return out
    }
    static func number(_ s: String?) -> Double? {
        guard let s = s?.trimmingCharacters(in: .whitespaces), !s.isEmpty else { return nil }
        if s.hasSuffix("%") { return Double(s.dropLast()).map { $0 / 100 } }
        return Double(s)
    }
    /// A length in user units ("12", "12px", "1.5pt" read as user units).
    static func length(_ s: String?) -> Double? {
        guard let s = s?.trimmingCharacters(in: .whitespaces), !s.isEmpty else { return nil }
        var scan = SVGScanner(s)
        return scan.number()
    }
    /// A gradient coordinate or offset: "0.5" or "50%".
    static func fraction(_ s: String?) -> Double? { number(s) }
    /// The id in "url(#id)".
    static func url(_ s: String) -> String? {
        guard let r = s.range(of: "url("), let end = s[r.upperBound...].firstIndex(of: ")") else { return nil }
        var id = s[r.upperBound..<end].trimmingCharacters(in: CharacterSet(charactersIn: " '\""))
        if id.hasPrefix("#") { id.removeFirst() }
        return id
    }

    static func color(_ raw: String, current: SVGColor) -> SVGColor? {
        let s = raw.trimmingCharacters(in: .whitespaces).lowercased()
        if s.isEmpty { return nil }
        if s == "currentcolor" { return current }
        if s.hasPrefix("#") {
            let hex = Array(s.dropFirst())
            func h(_ chars: ArraySlice<Character>) -> Double? { UInt8(String(chars), radix: 16).map { Double($0) / 255 } }
            switch hex.count {
            case 3, 4:
                let d = hex.map { [$0, $0] }
                guard let r = h(d[0][...]), let g = h(d[1][...]), let b = h(d[2][...]) else { return nil }
                return SVGColor(r: r, g: g, b: b, a: hex.count == 4 ? (h(d[3][...]) ?? 1) : 1)
            case 6, 8:
                guard let r = h(hex[0..<2]), let g = h(hex[2..<4]), let b = h(hex[4..<6]) else { return nil }
                return SVGColor(r: r, g: g, b: b, a: hex.count == 8 ? (h(hex[6..<8]) ?? 1) : 1)
            default: return nil
            }
        }
        if s.hasPrefix("rgb") {
            let inside = s.drop { $0 != "(" }.dropFirst().prefix { $0 != ")" }
            let parts = inside.split(whereSeparator: { $0 == "," || $0 == " " || $0 == "/" }).map(String.init)
            guard parts.count >= 3 else { return nil }
            func ch(_ p: String) -> Double { p.hasSuffix("%") ? (Double(p.dropLast()) ?? 0) / 100 : (Double(p) ?? 0) / 255 }
            let a = parts.count > 3 ? (parts[3].hasSuffix("%") ? (Double(parts[3].dropLast()) ?? 100) / 100 : Double(parts[3]) ?? 1) : 1
            return SVGColor(r: ch(parts[0]), g: ch(parts[1]), b: ch(parts[2]), a: a)
        }
        return named[s]
    }

    private static let named: [String: SVGColor] = {
        let table: [String: UInt32] = [
            "black": 0x000000, "white": 0xffffff, "red": 0xff0000, "green": 0x008000, "blue": 0x0000ff, "yellow": 0xffff00,
            "orange": 0xffa500, "purple": 0x800080, "gray": 0x808080, "grey": 0x808080, "silver": 0xc0c0c0, "maroon": 0x800000,
            "navy": 0x000080, "teal": 0x008080, "olive": 0x808000, "lime": 0x00ff00, "aqua": 0x00ffff, "cyan": 0x00ffff,
            "fuchsia": 0xff00ff, "magenta": 0xff00ff, "pink": 0xffc0cb, "brown": 0xa52a2a, "gold": 0xffd700, "indigo": 0x4b0082,
            "violet": 0xee82ee, "skyblue": 0x87ceeb, "lightgray": 0xd3d3d3, "lightgrey": 0xd3d3d3, "darkgray": 0xa9a9a9,
            "darkgrey": 0xa9a9a9, "beige": 0xf5f5dc, "coral": 0xff7f50, "crimson": 0xdc143c, "salmon": 0xfa8072, "tomato": 0xff6347,
            "khaki": 0xf0e68c, "lavender": 0xe6e6fa, "turquoise": 0x40e0d0, "tan": 0xd2b48c, "steelblue": 0x4682b4,
            "darkblue": 0x00008b, "darkgreen": 0x006400, "darkred": 0x8b0000, "lightblue": 0xadd8e6, "lightgreen": 0x90ee90,
        ]
        return table.mapValues { v in SVGColor(r: Double((v >> 16) & 0xff) / 255, g: Double((v >> 8) & 0xff) / 255, b: Double(v & 0xff) / 255) }
    }()
}

enum SVGTransform {
    /// "translate(10 20) rotate(30) scale(2)…", applied right to left (the last one first).
    static func parse(_ s: String) -> CGAffineTransform {
        var t = CGAffineTransform.identity
        var rest = Substring(s)
        while let open = rest.firstIndex(of: "("), let close = rest[open...].firstIndex(of: ")") {
            let name = rest[..<open].trimmingCharacters(in: CharacterSet(charactersIn: " ,\n\t"))
            let v = SVGNumbers.list(String(rest[rest.index(after: open)..<close]))
            var m = CGAffineTransform.identity
            switch name {
            case "translate": m = CGAffineTransform(translationX: v.first ?? 0, y: v.count > 1 ? v[1] : 0)
            case "scale": m = CGAffineTransform(scaleX: v.first ?? 1, y: v.count > 1 ? v[1] : (v.first ?? 1))
            case "rotate":
                let a = (v.first ?? 0) * .pi / 180
                if v.count >= 3 {
                    m = CGAffineTransform(translationX: v[1], y: v[2]).rotated(by: a).translatedBy(x: -v[1], y: -v[2])
                } else { m = CGAffineTransform(rotationAngle: a) }
            case "skewX": m = CGAffineTransform(a: 1, b: 0, c: tan((v.first ?? 0) * .pi / 180), d: 1, tx: 0, ty: 0)
            case "skewY": m = CGAffineTransform(a: 1, b: tan((v.first ?? 0) * .pi / 180), c: 0, d: 1, tx: 0, ty: 0)
            case "matrix" where v.count == 6: m = CGAffineTransform(a: v[0], b: v[1], c: v[2], d: v[3], tx: v[4], ty: v[5])
            default: break
            }
            t = m.concatenating(t)
            rest = rest[rest.index(after: close)...]
        }
        return t
    }
}

/// Numbers in SVG syntax, which needs no separators: "-42-24", ".5.5", "1e-3", and arc flags "01".
struct SVGScanner {
    private let chars: [Character]
    private(set) var i = 0
    init(_ s: String) { chars = Array(s) }
    var atEnd: Bool { mutating get { skip(); return i >= chars.count } }
    mutating func skip() { while i < chars.count, chars[i].isWhitespace || chars[i] == "," { i += 1 } }
    mutating func peek() -> Character? { skip(); return i < chars.count ? chars[i] : nil }
    mutating func letter() -> Character? {
        guard let c = peek(), c.isLetter, c != "e", c != "E" else { return nil }
        i += 1; return c
    }
    /// An arc's flag: one digit 0 or 1.
    mutating func flag() -> Bool? {
        guard let c = peek(), c == "0" || c == "1" else { return nil }
        i += 1; return c == "1"
    }
    mutating func number() -> Double? {
        skip()
        let start = i
        if i < chars.count, chars[i] == "+" || chars[i] == "-" { i += 1 }
        var digits = false, dot = false
        while i < chars.count {
            let c = chars[i]
            if c.isASCII && c.isNumber { digits = true; i += 1 }
            else if c == ".", !dot { dot = true; i += 1 }
            else { break }
        }
        if digits, i < chars.count, chars[i] == "e" || chars[i] == "E" {
            var j = i + 1
            if j < chars.count, chars[j] == "+" || chars[j] == "-" { j += 1 }
            if j < chars.count, chars[j].isASCII, chars[j].isNumber {
                i = j
                while i < chars.count, chars[i].isASCII, chars[i].isNumber { i += 1 }
            }
        }
        guard digits else { i = start; return nil }
        return Double(String(chars[start..<i]))
    }
}

/// A path's `d`, every command (M L H V C S Q T A Z, absolute and relative), arcs as Béziers.
enum SVGPathData {
    static func append(_ d: String, to p: CGMutablePath) {
        var s = SVGScanner(d)
        var cur = CGPoint.zero, start = CGPoint.zero
        var lastCtrl: CGPoint?, lastQuad: CGPoint?
        var cmd: Character = "M"
        var first = true
        while !s.atEnd {
            if let c = s.letter() { cmd = c } else if first { return }
            first = false
            let rel = cmd.isLowercase
            func pt(_ x: Double, _ y: Double) -> CGPoint { rel ? CGPoint(x: cur.x + x, y: cur.y + y) : CGPoint(x: x, y: y) }
            switch cmd.uppercased().first! {
            case "M":
                guard let x = s.number(), let y = s.number() else { return }
                cur = pt(x, y); start = cur; p.move(to: cur)
                cmd = rel ? "l" : "L"                                   // more pairs are lines
                lastCtrl = nil; lastQuad = nil
            case "L":
                guard let x = s.number(), let y = s.number() else { return }
                cur = pt(x, y); p.addLine(to: cur); lastCtrl = nil; lastQuad = nil
            case "H":
                guard let x = s.number() else { return }
                cur = CGPoint(x: rel ? cur.x + x : x, y: cur.y); p.addLine(to: cur); lastCtrl = nil; lastQuad = nil
            case "V":
                guard let y = s.number() else { return }
                cur = CGPoint(x: cur.x, y: rel ? cur.y + y : y); p.addLine(to: cur); lastCtrl = nil; lastQuad = nil
            case "C":
                guard let x1 = s.number(), let y1 = s.number(), let x2 = s.number(), let y2 = s.number(),
                      let x = s.number(), let y = s.number() else { return }
                let c1 = pt(x1, y1), c2 = pt(x2, y2), e = pt(x, y)
                p.addCurve(to: e, control1: c1, control2: c2); cur = e; lastCtrl = c2; lastQuad = nil
            case "S":
                guard let x2 = s.number(), let y2 = s.number(), let x = s.number(), let y = s.number() else { return }
                let c1 = lastCtrl.map { CGPoint(x: 2 * cur.x - $0.x, y: 2 * cur.y - $0.y) } ?? cur
                let c2 = pt(x2, y2), e = pt(x, y)
                p.addCurve(to: e, control1: c1, control2: c2); cur = e; lastCtrl = c2; lastQuad = nil
            case "Q":
                guard let x1 = s.number(), let y1 = s.number(), let x = s.number(), let y = s.number() else { return }
                let c = pt(x1, y1), e = pt(x, y)
                p.addQuadCurve(to: e, control: c); cur = e; lastQuad = c; lastCtrl = nil
            case "T":
                guard let x = s.number(), let y = s.number() else { return }
                let c = lastQuad.map { CGPoint(x: 2 * cur.x - $0.x, y: 2 * cur.y - $0.y) } ?? cur
                let e = pt(x, y)
                p.addQuadCurve(to: e, control: c); cur = e; lastQuad = c; lastCtrl = nil
            case "A":
                guard let rx = s.number(), let ry = s.number(), let rot = s.number(), let large = s.flag(), let sweep = s.flag(),
                      let x = s.number(), let y = s.number() else { return }
                let e = pt(x, y)
                arc(p, from: cur, to: e, rx: abs(rx), ry: abs(ry), rotation: rot * .pi / 180, large: large, sweep: sweep)
                cur = e; lastCtrl = nil; lastQuad = nil
            case "Z":
                p.closeSubpath(); cur = start; lastCtrl = nil; lastQuad = nil
            default:
                return
            }
        }
    }

    /// An elliptical arc as cubic Béziers (SVG's endpoint parameterization, W3C appendix F.6).
    static func arc(_ p: CGMutablePath, from a: CGPoint, to b: CGPoint, rx rx0: Double, ry ry0: Double, rotation phi: Double,
                    large: Bool, sweep: Bool) {
        guard a != b else { return }
        guard rx0 > 0, ry0 > 0 else { p.addLine(to: b); return }
        let cphi = cos(phi), sphi = sin(phi)
        let dx = (a.x - b.x) / 2, dy = (a.y - b.y) / 2
        let x1 = cphi * dx + sphi * dy, y1 = -sphi * dx + cphi * dy
        var rx = rx0, ry = ry0
        let lambda = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
        if lambda > 1 { rx *= lambda.squareRoot(); ry *= lambda.squareRoot() }
        let num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
        let den = rx * rx * y1 * y1 + ry * ry * x1 * x1
        var k = den == 0 ? 0 : (max(0, num) / den).squareRoot()
        if large == sweep { k = -k }
        let cx1 = k * rx * y1 / ry, cy1 = -k * ry * x1 / rx
        let cx = cphi * cx1 - sphi * cy1 + (a.x + b.x) / 2, cy = sphi * cx1 + cphi * cy1 + (a.y + b.y) / 2
        func angle(_ ux: Double, _ uy: Double, _ vx: Double, _ vy: Double) -> Double {
            let a = atan2(ux * vy - uy * vx, ux * vx + uy * vy)
            return a
        }
        let th1 = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
        var dth = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
        if !sweep, dth > 0 { dth -= 2 * .pi } else if sweep, dth < 0 { dth += 2 * .pi }
        let segments = max(1, Int((abs(dth) / (.pi / 2)).rounded(.up)))
        let step = dth / Double(segments)
        let t = 4.0 / 3.0 * tan(step / 4)
        func point(_ th: Double) -> CGPoint {
            CGPoint(x: cx + rx * cos(th) * cphi - ry * sin(th) * sphi, y: cy + rx * cos(th) * sphi + ry * sin(th) * cphi)
        }
        func deriv(_ th: Double) -> CGPoint {
            CGPoint(x: -rx * sin(th) * cphi - ry * cos(th) * sphi, y: -rx * sin(th) * sphi + ry * cos(th) * cphi)
        }
        var th = th1
        for k in 0..<segments {
            let th2 = th + step
            let p1 = point(th), p2 = k == segments - 1 ? b : point(th2)
            let d1 = deriv(th), d2 = deriv(th2)
            p.addCurve(to: p2, control1: CGPoint(x: p1.x + t * d1.x, y: p1.y + t * d1.y),
                       control2: CGPoint(x: p2.x - t * d2.x, y: p2.y - t * d2.y))
            th = th2
        }
    }
}
