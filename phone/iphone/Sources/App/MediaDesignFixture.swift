import UIKit

/// A local, reproducible artwork for native preview/layout tests; never shown in a live account.
enum MediaDesignFixture {
    static var enabled: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--demo") && ProcessInfo.processInfo.arguments.contains("--media-fixture")
        #else
        false
        #endif
    }
    @MainActor static var image: Data {
        UIGraphicsImageRenderer(size: CGSize(width: 800, height: 520)).pngData { context in
            let ctx = context.cgContext
            let colors = [UIColor(red: 0.08, green: 0.17, blue: 0.26, alpha: 1).cgColor, UIColor(red: 0.43, green: 0.59, blue: 0.63, alpha: 1).cgColor]
            let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 1])!
            ctx.drawLinearGradient(gradient, start: .zero, end: CGPoint(x: 800, y: 520), options: [])
            UIColor(red: 0.98, green: 0.72, blue: 0.47, alpha: 1).setFill()
            ctx.fillEllipse(in: CGRect(x: 510, y: 100, width: 120, height: 120))
            let hill = UIBezierPath(); hill.move(to: CGPoint(x: 0, y: 350))
            hill.addCurve(to: CGPoint(x: 800, y: 290), controlPoint1: CGPoint(x: 260, y: 180), controlPoint2: CGPoint(x: 590, y: 450))
            hill.addLine(to: CGPoint(x: 800, y: 520)); hill.addLine(to: CGPoint(x: 0, y: 520)); hill.close()
            UIColor(red: 0.12, green: 0.30, blue: 0.35, alpha: 1).setFill(); hill.fill()
            let foreground = UIBezierPath(); foreground.move(to: CGPoint(x: 0, y: 430))
            foreground.addCurve(to: CGPoint(x: 800, y: 380), controlPoint1: CGPoint(x: 220, y: 510), controlPoint2: CGPoint(x: 530, y: 280))
            foreground.addLine(to: CGPoint(x: 800, y: 520)); foreground.addLine(to: CGPoint(x: 0, y: 520)); foreground.close()
            UIColor(red: 0.06, green: 0.19, blue: 0.24, alpha: 1).setFill(); foreground.fill()
        }
    }
}
