import CoreGraphics
import Foundation
import Testing
@testable import AbstractGatewayClient

/// Drawings an agent wrote (two of them verbatim), read into what the watch draws.
private let hero = #"""
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000" role="img" aria-label="Abstract AI orchestration modules">
  <defs>
    <linearGradient id="bg" x2="1" y2="1"><stop stop-color="#05081a"/><stop offset=".48" stop-color="#0b1234"/><stop offset="1" stop-color="#17092f"/></linearGradient>
    <radialGradient id="glow"><stop stop-color="#77f7ff" stop-opacity=".72"/><stop offset=".34" stop-color="#6366ff" stop-opacity=".2"/><stop offset="1" stop-color="#09112b" stop-opacity="0"/></radialGradient>
    <linearGradient id="glass" x2="1" y2="1"><stop stop-color="#e9ffff" stop-opacity=".22"/><stop offset="1" stop-color="#6671ff" stop-opacity=".06"/></linearGradient>
    <linearGradient id="line" x2="1"><stop stop-color="#62f6ff" stop-opacity="0"/><stop offset=".5" stop-color="#9f8cff"/><stop offset="1" stop-color="#62f6ff" stop-opacity="0"/></linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="24"/></filter><filter id="shadow"><feDropShadow dx="0" dy="22" stdDeviation="24" flood-color="#00051a" flood-opacity=".75"/></filter>
  </defs>
  <rect width="1600" height="1000" fill="url(#bg)"/>
  <ellipse cx="800" cy="490" rx="640" ry="520" fill="url(#glow)"/>
  <g opacity=".22" stroke="#8ccfff" fill="none"><path d="M0 160H1600M0 360H1600M0 560H1600M0 760H1600"/><path d="M220 0V1000M520 0V1000M820 0V1000M1120 0V1000M1420 0V1000"/></g>
  <g fill="none" stroke="url(#line)" stroke-width="3" opacity=".9"><path d="M260 660C390 660 380 490 528 490"/><path d="M1070 490c160 0 130-190 270-190"/><path d="M520 750c160 0 135-135 278-135"/><path d="M1040 650c120 0 110 120 260 120"/></g>
  <g fill="#8dffff"><circle cx="260" cy="660" r="6"/><circle cx="528" cy="490" r="7"/><circle cx="1340" cy="300" r="6"/><circle cx="1300" cy="770" r="6"/></g>
  <g filter="url(#shadow)" stroke="#c2f8ff" stroke-opacity=".35">
    <g transform="translate(510 280)"><rect width="265" height="185" rx="20" fill="url(#glass)"/><path d="M28 47h73M28 72h119M28 129h206" stroke="#bdffff" stroke-opacity=".65" stroke-width="4" stroke-linecap="round"/><circle cx="214" cy="55" r="21" fill="#7df5ff" fill-opacity=".82" stroke="none"/></g>
    <g transform="translate(842 390)"><rect width="285" height="210" rx="22" fill="url(#glass)"/><path d="M32 50h83M32 78h178M32 145h220M32 169h142" stroke="#d6d7ff" stroke-opacity=".64" stroke-width="4" stroke-linecap="round"/><path d="M220 50l25 25-25 25-25-25z" fill="#a78bfa" fill-opacity=".85" stroke="none"/></g>
    <g transform="translate(585 590)"><rect width="305" height="198" rx="22" fill="url(#glass)"/><path d="M34 55h104M34 82h194M34 146h239" stroke="#d2ffff" stroke-opacity=".62" stroke-width="4" stroke-linecap="round"/><circle cx="242" cy="66" r="24" fill="#6a72ff" fill-opacity=".8" stroke="none"/></g>
  </g>
  <g transform="translate(800 505)" filter="url(#shadow)"><circle r="115" fill="#111c49" stroke="#9bfbff" stroke-width="2"/><circle r="84" fill="none" stroke="#806cff" stroke-width="2" stroke-dasharray="6 10"/><path d="M-42-24L0-50 42-24v48L0 50-42 24z" fill="#91faff" fill-opacity=".9"/><circle r="14" fill="#151c53"/></g>
  <g fill="#e8ffff" font-family="Arial, sans-serif" text-anchor="middle"><text x="800" y="890" font-size="22" letter-spacing="9" opacity=".72">ORCHESTRATE · GENERATE · DEPLOY</text></g>
  <g fill="#88efff" opacity=".8"><circle cx="102" cy="120" r="2"/><circle cx="180" cy="800" r="3"/><circle cx="1450" cy="190" r="3"/><circle cx="1510" cy="690" r="2"/><circle cx="1210" cy="870" r="3"/></g>
</svg>
"""#

private let minimalWhite = #"""
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000" role="img" aria-label="Minimal AbstractFramework illustration">
  <rect width="1600" height="1000" fill="#ffffff"/>
  <g fill="none" stroke="#111827" stroke-linecap="round" stroke-linejoin="round">
    <path d="M390 590C510 390 653 363 800 500C947 637 1090 610 1210 410" stroke-width="10"/>
    <path d="M470 690C600 570 695 585 800 680C905 775 1000 790 1130 655" stroke="#c7d2fe" stroke-width="7"/>
    <path d="M505 325C625 435 710 402 800 310C890 218 975 185 1095 295" stroke="#e0e7ff" stroke-width="7"/>
  </g>
  <circle cx="800" cy="500" r="54" fill="#111827"/>
  <circle cx="800" cy="500" r="18" fill="#ffffff"/>
  <g fill="#111827"><circle cx="390" cy="590" r="12"/><circle cx="1210" cy="410" r="12"/></g>
  <text x="800" y="850" text-anchor="middle" fill="#111827" font-family="Arial, Helvetica, sans-serif" font-size="27" font-weight="600" letter-spacing="7">ABSTRACTFRAMEWORK</text>
</svg>
"""#

private func doc(_ s: String) throws -> SVGDocument { try SVGDocument.parse(Data(s.utf8)) }
private func path(_ d: String) -> CGPath { let p = CGMutablePath(); SVGPathData.append(d, to: p); return p }
private func near(_ a: CGFloat, _ b: CGFloat, _ e: CGFloat = 0.01) -> Bool { abs(a - b) < e }

@Test func pathNumbersNeedNoSeparators() {
    // Signs and dots start a new number: "-42-24", ".5.5"; a relative v after absolute L.
    let b = path("M-42-24L0-50 42-24v48L0 50-42 24z").boundingBoxOfPath
    #expect(near(b.minX, -42) && near(b.maxX, 42) && near(b.minY, -50) && near(b.maxY, 50))
    let dots = path("M.5.5l.5.5").boundingBoxOfPath
    #expect(near(dots.minX, 0.5) && near(dots.maxX, 1) && near(dots.maxY, 1))
    // Repeated pairs after M are lines; H and V, relative and absolute.
    let grid = path("M0 160H1600M0 360H1600").boundingBoxOfPath
    #expect(near(grid.maxX, 1600) && near(grid.minY, 160) && near(grid.maxY, 360))
    #expect(near(path("M10 10 20 20 30 10").boundingBoxOfPath.maxX, 30))
}

@Test func arcsAreDrawnOnTheRightSide() {
    // From (0,0) to (20,0), radius 10: sweep 1 bulges up (y down), sweep 0 down.
    let up = path("M0 0A10 10 0 0 1 20 0").boundingBoxOfPath
    #expect(near(up.minY, -10, 0.05) && near(up.maxY, 0, 0.05) && near(up.maxX, 20))
    let down = path("M0 0A10 10 0 0 0 20 0").boundingBoxOfPath
    #expect(near(down.maxY, 10, 0.05))
    // Flags may be packed against the next number ("0120" is 0, 1, 20).
    let packed = path("M0 0a10 10 0 0120 0").boundingBoxOfPath
    #expect(near(packed.minY, -10, 0.05) && near(packed.maxX, 20))
    // A quarter: the small arc stays inside the square its ends span, the large one goes round.
    let small = path("M0 0A10 10 0 0 1 10 10").boundingBoxOfPath
    #expect(small.maxX < 10.05 && small.maxY < 10.05 && small.minX > -0.05)
    let large = path("M0 0A10 10 0 1 1 10 10").boundingBoxOfPath
    #expect(near(large.width, 20, 0.1) && near(large.height, 20, 0.1))
    // Too small a radius is scaled up to reach the end.
    let scaled = path("M0 0A1 1 0 0 1 20 0").boundingBoxOfPath
    #expect(near(scaled.minY, -10, 0.05))
}

@Test func coloursInEveryNotation() {
    #expect(SVGNumbers.color("#fff", current: .black) == SVGColor(r: 1, g: 1, b: 1))
    #expect(SVGNumbers.color("#ff000080", current: .black).map { near($0.a, 0.502) && $0.r == 1 } == true)
    #expect(SVGNumbers.color("rgb(255, 0, 0)", current: .black) == SVGColor(r: 1, g: 0, b: 0))
    #expect(SVGNumbers.color("rgba(0,0,0,.5)", current: .black)?.a == 0.5)
    #expect(SVGNumbers.color("steelblue", current: .black) != nil)
    #expect(SVGNumbers.color("currentColor", current: SVGColor(r: 0, g: 1, b: 0)) == SVGColor(r: 0, g: 1, b: 0))
}

@Test func transformsComposeInOrder() {
    let t = SVGTransform.parse("translate(10 20) scale(2)")
    let p = CGPoint(x: 1, y: 1).applying(t)
    #expect(near(p.x, 12) && near(p.y, 22))                      // scaled first, then moved
    let r = CGPoint(x: 1, y: 0).applying(SVGTransform.parse("rotate(90)"))
    #expect(near(r.x, 0) && near(r.y, 1))
}

@Test func aMinimalDrawingWithItsGroupsStylesAndText() throws {
    let d = try doc(minimalWhite)
    #expect(d.viewBox == CGRect(x: 0, y: 0, width: 1600, height: 1000))
    #expect(d.nodes.count == 9)                                  // rect, 3 paths, 2 + 2 circles, the title
    // The group's stroke and "no fill" reach its paths; a path's own stroke wins.
    let first = d.nodes[1], second = d.nodes[2]
    guard case .color(let s1)? = first.style.stroke, case .color(let s2)? = second.style.stroke else { Issue.record("no stroke"); return }
    #expect(near(s1.r, 0x11 / 255.0) && near(s2.r, 0xc7 / 255.0))
    #expect(first.style.fill == nil && first.style.strokeWidth == 10 && first.style.lineCap == .round)
    guard case .text(let words, let at) = d.nodes[8].kind else { Issue.record("no text"); return }
    #expect(words == "ABSTRACTFRAMEWORK" && at == CGPoint(x: 800, y: 850))
    #expect(d.nodes[8].style.anchor == "middle" && d.nodes[8].style.fontSize == 27 && d.nodes[8].style.fontWeight == 600)
    #expect(d.nodes[8].style.letterSpacing == 7)
}

@Test func gradientsFiltersAndTransformsOfARicherDrawing() throws {
    let d = try doc(hero)
    // The background: a bounding-box linear gradient, corner to corner, three stops.
    guard case .gradient(let bg)? = d.nodes[0].style.fill, case .linear(_, _, let x2, let y2) = bg.kind else { Issue.record("no gradient"); return }
    #expect(!bg.userSpace && x2 == 1 && y2 == 1 && bg.stops.count == 3 && near(bg.stops[1].offset, 0.48))
    // The glow: a radial gradient, its first stop at .72 opacity.
    guard case .gradient(let glow)? = d.nodes[1].style.fill, case .radial = glow.kind else { Issue.record("no radial"); return }
    #expect(near(glow.stops[0].color.a, 0.72))
    // A group's opacity reaches its children; a filter's shadow too; a translate moves a card.
    #expect(near(d.nodes[2].style.opacity, 0.22))
    let card = d.nodes.first { node in
        if case .shape(let p) = node.kind { return near(p.boundingBoxOfPath.width, 265) } else { return false }
    }
    #expect(card.map { near($0.transform.tx, 510) && near($0.transform.ty, 280) } == true)
    #expect(card.map { $0.effects.contains { if case .shadow(_, let dy, _, _) = $0 { return dy == 22 } else { return false } } } == true)
    let dashed = d.nodes.first { !$0.style.dash.isEmpty }
    #expect(dashed?.style.dash == [6, 10])
    // The tagline, with a letter spacing.
    #expect(d.nodes.contains { if case .text(let w, _) = $0.kind { return w.hasPrefix("ORCHESTRATE") } else { return false } })
}

@Test func notAnSVGIsRefused() {
    #expect(throws: (any Error).self) { try SVGDocument.parse(Data("<html><body/></html>".utf8)) }
    #expect(throws: (any Error).self) { try SVGDocument.parse(Data("not xml".utf8)) }
}
