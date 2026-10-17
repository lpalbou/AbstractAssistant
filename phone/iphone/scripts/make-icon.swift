import AppKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let side = 1024
let context = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8, bytesPerRow: side * 4,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
context.setFillColor(NSColor(red: 0.035, green: 0.045, blue: 0.085, alpha: 1).cgColor)
context.fill(CGRect(x: 0, y: 0, width: side, height: side))
context.translateBy(x: 512, y: 512)
for i in 0..<7 {
    context.saveGState(); context.rotate(by: CGFloat(i) * .pi / 7)
    context.setStrokeColor(NSColor(red: 0.45 + Double(i) * 0.035, green: 0.86 - Double(i) * 0.025, blue: 0.91, alpha: 0.85).cgColor)
    context.setLineWidth(i == 3 ? 7 : 3)
    context.strokeEllipse(in: CGRect(x: -310, y: -200, width: 620, height: 400))
    context.restoreGState()
}
context.setFillColor(NSColor.white.cgColor); context.fillEllipse(in: CGRect(x: 192, y: 204, width: 15, height: 15))
let output = CommandLine.arguments.dropFirst().first ?? "Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: output) as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(destination, context.makeImage()!, nil)
guard CGImageDestinationFinalize(destination) else { fatalError("Could not write app icon") }
