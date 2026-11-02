import Foundation
import Testing
@testable import AbstractGatewayClient

/// "Your Mac may be asleep." appears only when the gateway's computer did not answer.
@Suite struct GatewayReachTests {
    @Test func aComputerThatDoesNotAnswerMayBeAsleep() {
        for code in [URLError.Code.timedOut, .cannotConnectToHost, .cannotFindHost, .networkConnectionLost, .secureConnectionFailed] {
            #expect(GatewayReach.mayBeAsleep(URLError(code)), "\(code)")
        }
        #expect(GatewayReach.mayBeAsleep(GatewayError.invalidResponse))
        #expect(GatewayReach.mayBeAsleep(GatewayError.http(status: 502, body: "")))
        #expect(GatewayReach.mayBeAsleep(GatewayError.http(status: 504, body: "")))
        #expect(GatewayReach.mayBeAsleep(GatewaySignIn.Failure.unreachable("Can't reach the server.")))
    }

    @Test func thisDeviceOfflineOrAnAnswerFromTheGatewayIsNotSleep() {
        for code in [URLError.Code.notConnectedToInternet, .dataNotAllowed, .cancelled] {
            #expect(!GatewayReach.mayBeAsleep(URLError(code)), "\(code)")
        }
        #expect(!GatewayReach.mayBeAsleep(GatewayError.unauthorized))
        #expect(!GatewayReach.mayBeAsleep(GatewayError.alreadyHandled))
        #expect(!GatewayReach.mayBeAsleep(GatewayError.http(status: 500, body: "")))
        #expect(!GatewayReach.mayBeAsleep(GatewayError.http(status: 404, body: "")))
        #expect(!GatewayReach.mayBeAsleep(GatewaySignIn.Failure.refused("Wrong code.")))
        #expect(!GatewayReach.mayBeAsleep(CancellationError()))
        #expect(GatewayReach.asleepHint == "Your Mac may be asleep.")
    }
}
