import SwiftUI

/// The same five cords move from orbit loops to a triangulated sphere or raised-hand outline.
/// Geometry is sampled in normalized coordinates so transitions work at every rendered size.
struct OrbWeave: View {
    var stop: Double
    var geodesic: Double
    var approval: Double
    var energy: Double
    var time: Double
    var body: some View {
        Canvas { context, size in
            let hand = min(1, max(0, approval)), geo = min(1, max(0, geodesic))
            let total = max(1, hand + geo), h = hand / total, g = geo / total
            let projected = Self.mesh.vertices.map { $0.projected(time: time) }
            let perCord = Self.mesh.edges.count / 5
            for (edgeIndex, edge) in Self.mesh.edges.enumerated() {
                let cord = edgeIndex % 5, section = edgeIndex / 5
                let a = projected[edge.0], b = projected[edge.1]
                var path = Path()
                for sample in 0...8 {
                    let fraction = Double(sample) / 8
                    let along = (Double(section) + fraction) / Double(perCord)
                    let source = orbit(along, cord: cord)
                    let globe = CGPoint(x: 0.5 + (a.x + (b.x - a.x) * fraction) * 0.57,
                                        y: 0.5 + (a.y + (b.y - a.y) * fraction) * 0.57)
                    let target = Self.handPoint(along, cord: cord, time: time)
                    let point = CGPoint(x: (source.x * (1 - g - h) + globe.x * g + target.x * h) * size.width,
                                        y: (source.y * (1 - g - h) + globe.y * g + target.y * h) * size.height)
                    if sample == 0 { path.move(to: point) } else { path.addLine(to: point) }
                }
                let depth = (a.z + b.z + 2) / 4
                let flow = 0.5 + 0.5 * sin(time * 5 - Double(edgeIndex) * 0.29)
                let base = cord % 2 == 0 ? (0.42, 0.89, 0.80) : (0.68, 0.65, 1.0)
                let color = Color(red: base.0 + (1 - base.0) * h,
                                  green: base.1 + (0.61 - base.1) * h,
                                  blue: base.2 + (0.20 - base.2) * h)
                context.stroke(path, with: .color(color.opacity((0.35 + depth * 0.55) * (1 - h) + (0.48 + flow * 0.48) * h)),
                               style: StrokeStyle(lineWidth: max(0.65, size.width / 88) * (0.75 + depth * 0.5 + h * 0.3), lineCap: .round, lineJoin: .round))
            }
        }
        .shadow(color: .orange.opacity(approval * 0.4), radius: 5)
    }
    private func orbit(_ fraction: Double, cord: Int) -> CGPoint {
        let angle = fraction * .pi * 2
        let exponent = 2 / (2 + 5 * stop)
        let ripple = energy * (0.19 * sin(angle * 3 + time * 3 + Double(cord) * 1.7) + 0.075 * sin(angle * 7 - time * 3))
        let x = cos(angle), y = sin(angle)
        let px = (x < 0 ? -1.0 : 1) * pow(abs(x), exponent) * (0.53 + Double(cord) * 0.055 + energy * 0.16) * 0.5 * (1 + ripple)
        let py = (y < 0 ? -1.0 : 1) * pow(abs(y), exponent) * (0.39 + energy * 0.33 + stop * 0.16) * 0.5 * (1 + ripple)
        let rotation = (Double(cord) * 34 + time * 9 + energy * Double(cord - 2) * 28) * .pi / 180
        return CGPoint(x: 0.5 + px * cos(rotation) - py * sin(rotation), y: 0.5 + px * sin(rotation) + py * cos(rotation))
    }
    private static func handPoint(_ fraction: Double, cord: Int, time: Double) -> CGPoint {
        let position = fraction.truncatingRemainder(dividingBy: 1) * Double(hand.count)
        let index = Int(position), part = position - Double(index)
        let a = hand[index], b = hand[(index + 1) % hand.count]
        let scale = 0.94 + Double(cord) * 0.025
        let wave = sin(fraction * .pi * 8 + time * 3.8 + Double(cord)) * 0.003
        return CGPoint(x: 0.5 + (a.x + (b.x - a.x) * part - 0.435) * scale + wave,
                       y: 0.5 + (a.y + (b.y - a.y) * part - 0.5) * scale + wave * 0.6)
    }
    /// Round the finger caps, then resample by distance: cords don't bunch up at control points.
    private static let hand: [CGPoint] = {
        var points: [CGPoint] = [
            .init(x: 0.38, y: 0.90), .init(x: 0.31, y: 0.78), .init(x: 0.22, y: 0.67),
            .init(x: 0.13, y: 0.56), .init(x: 0.13, y: 0.51), .init(x: 0.17, y: 0.48), .init(x: 0.21, y: 0.50), .init(x: 0.29, y: 0.60),
            .init(x: 0.29, y: 0.28), .init(x: 0.31, y: 0.22), .init(x: 0.35, y: 0.22), .init(x: 0.38, y: 0.25), .init(x: 0.38, y: 0.48), .init(x: 0.40, y: 0.49),
            .init(x: 0.41, y: 0.16), .init(x: 0.43, y: 0.11), .init(x: 0.47, y: 0.11), .init(x: 0.50, y: 0.15), .init(x: 0.50, y: 0.46), .init(x: 0.52, y: 0.47),
            .init(x: 0.53, y: 0.22), .init(x: 0.55, y: 0.17), .init(x: 0.59, y: 0.17), .init(x: 0.62, y: 0.21), .init(x: 0.62, y: 0.51), .init(x: 0.64, y: 0.52),
            .init(x: 0.65, y: 0.34), .init(x: 0.67, y: 0.29), .init(x: 0.71, y: 0.30), .init(x: 0.74, y: 0.34), .init(x: 0.74, y: 0.65),
            .init(x: 0.72, y: 0.75), .init(x: 0.65, y: 0.83), .init(x: 0.63, y: 0.90)
        ]
        for _ in 0..<2 {
            points = points.indices.flatMap { index -> [CGPoint] in
                let a = points[index], b = points[(index + 1) % points.count]
                return [CGPoint(x: a.x * 0.75 + b.x * 0.25, y: a.y * 0.75 + b.y * 0.25),
                        CGPoint(x: a.x * 0.25 + b.x * 0.75, y: a.y * 0.25 + b.y * 0.75)]
            }
        }
        var distances = [0.0]
        for index in points.indices {
            let a = points[index], b = points[(index + 1) % points.count]
            distances.append(distances.last! + hypot(b.x - a.x, b.y - a.y))
        }
        return (0..<240).map { index in
            let distance = distances.last! * Double(index) / 240
            let segment = max(0, (distances.firstIndex(where: { $0 > distance }) ?? points.count) - 1)
            let a = points[segment], b = points[(segment + 1) % points.count]
            let part = (distance - distances[segment]) / max(0.000001, distances[segment + 1] - distances[segment])
            return CGPoint(x: a.x + (b.x - a.x) * part, y: a.y + (b.y - a.y) * part)
        }
    }()
    private struct Vertex: Sendable {
        var x: Double; var y: Double; var z: Double
        var normalized: Vertex { let n = sqrt(x*x + y*y + z*z); return .init(x: x/n, y: y/n, z: z/n) }
        func projected(time: Double) -> Vertex {
            let yaw = time * 1.9, pitch = time * 0.83 + 0.4
            let a = x * cos(yaw) + z * sin(yaw), b = -x * sin(yaw) + z * cos(yaw)
            let ry = y * cos(pitch) - b * sin(pitch), rz = y * sin(pitch) + b * cos(pitch)
            let perspective = 1 / (1.4 - rz * 0.22)
            return .init(x: a * perspective, y: ry * perspective, z: rz)
        }
    }
    private struct Mesh: Sendable { var vertices: [Vertex]; var edges: [(Int, Int)] }
    private static let mesh: Mesh = {
        let phi = (1 + sqrt(5.0)) / 2
        var vertices: [Vertex] = []
        for a in [-1.0, 1] { for b in [-phi, phi] {
            vertices += [Vertex(x: 0, y: a, z: b).normalized, Vertex(x: a, y: b, z: 0).normalized, Vertex(x: b, y: 0, z: a).normalized]
        } }
        func near(_ a: Int, _ b: Int) -> Bool {
            let u = vertices[a], v = vertices[b]
            return pow(u.x-v.x, 2) + pow(u.y-v.y, 2) + pow(u.z-v.z, 2) < 1.11
        }
        var midpoint: [String: Int] = [:], edgeSet = Set<String>(), edges: [(Int, Int)] = []
        func key(_ a: Int, _ b: Int) -> String { "\(min(a,b)):\(max(a,b))" }
        func middle(_ a: Int, _ b: Int) -> Int {
            let k = key(a,b); if let index = midpoint[k] { return index }
            let u = vertices[a], v = vertices[b], index = vertices.count
            vertices.append(Vertex(x: u.x+v.x, y: u.y+v.y, z: u.z+v.z).normalized); midpoint[k] = index; return index
        }
        func add(_ a: Int, _ b: Int) { if edgeSet.insert(key(a,b)).inserted { edges.append((a,b)) } }
        for a in 0..<12 { for b in (a+1)..<12 where near(a,b) { for c in (b+1)..<12 where near(a,c) && near(b,c) {
            let ab = middle(a,b), bc = middle(b,c), ca = middle(c,a)
            for (u,v) in [(a,ab),(ab,b),(b,bc),(bc,c),(c,ca),(ca,a),(ab,bc),(bc,ca),(ca,ab)] { add(u,v) }
        } } }
        return Mesh(vertices: vertices, edges: edges)
    }()
}
