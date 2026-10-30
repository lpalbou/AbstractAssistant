import XCTest
@testable import AbstractAssistantPhone

@MainActor
private final class TapProbe {
    var routed: [Int] = []
    var completions = 0
}

final class PhoneNotifierTests: XCTestCase {
    @MainActor func testBackgroundTapRoutesAndCompletesOnMainThread() async {
        let probe = TapProbe(), done = expectation(description: "Notification completed")
        done.assertForOverFulfill = true
        let previous = PhoneNotifier.shared.open
        defer { PhoneNotifier.shared.open = previous }
        PhoneNotifier.shared.open = { tab in
            XCTAssertTrue(Thread.isMainThread)
            probe.routed.append(tab)
        }
        Task.detached {
            PhoneNotifier.completeTap(destination: 1) {
                let completedOnMainThread = Thread.isMainThread
                Task { @MainActor in
                    XCTAssertTrue(completedOnMainThread)
                    XCTAssertEqual(probe.routed, [1])
                    probe.completions += 1
                    done.fulfill()
                }
            }
        }
        await fulfillment(of: [done], timeout: 3)
        XCTAssertEqual(probe.completions, 1)
    }

    @MainActor func testDismissedAndUnknownTapsStillCompleteWithoutOpeningATab() async {
        let probe = TapProbe(), done = expectation(description: "All notifications completed")
        done.expectedFulfillmentCount = 2; done.assertForOverFulfill = true
        let previous = PhoneNotifier.shared.open
        defer { PhoneNotifier.shared.open = previous }
        PhoneNotifier.shared.open = { probe.routed.append($0) }
        for destination in [nil, 99] as [Int?] {
            Task.detached {
                PhoneNotifier.completeTap(destination: destination) {
                    let completedOnMainThread = Thread.isMainThread
                    Task { @MainActor in
                        XCTAssertTrue(completedOnMainThread)
                        probe.completions += 1
                        done.fulfill()
                    }
                }
            }
        }
        await fulfillment(of: [done], timeout: 3)
        XCTAssertEqual(probe.routed, [])
        XCTAssertEqual(probe.completions, 2)
    }
}
