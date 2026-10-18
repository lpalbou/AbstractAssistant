import Foundation
import XCTest

/// Live tests write into a real gateway: each one names its conversation (`--test-session-id`)
/// and archives it when it ends, so nothing it asked stays in the person's Sessions.
enum LiveConversation {
    static func newId() -> String { "watch-test-" + UUID().uuidString.lowercased() }

    static func archive(_ sessionId: String, url: String, token: String) {
        guard let endpoint = URL(string: url)?.appending(path: "api/gateway/sessions/\(sessionId)/archive") else { return }
        var req = URLRequest(url: endpoint); req.httpMethod = "POST"; req.timeoutInterval = 30
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let done = XCTestExpectation(description: "archived")
        URLSession.shared.dataTask(with: req) { _, response, _ in
            print("archived \(sessionId): \((response as? HTTPURLResponse)?.statusCode ?? 0)")
            done.fulfill()
        }.resume()
        _ = XCTWaiter.wait(for: [done], timeout: 35)
    }
}

extension XCUIApplication {
    /// Scrolls a list a third of the screen (a swipe moves more than a screen and skips past a row).
    func nudgeUp() {
        let from = coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
        from.press(forDuration: 0.05, thenDragTo: coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.42)))
        usleep(500_000)
    }

    /// Scrolls back a fifth of the screen (a row stopped under the title bar comes out from under it).
    func nudgeDown() {
        let from = coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.4))
        from.press(forDuration: 0.05, thenDragTo: coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.62)))
        usleep(500_000)
    }
}
