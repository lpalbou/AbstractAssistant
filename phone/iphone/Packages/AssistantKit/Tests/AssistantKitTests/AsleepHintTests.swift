import Foundation
import Testing
import AssistantKit
import AbstractGatewayClient

/// The iPhone says "Your Mac may be asleep." exactly when the gateway's computer did not answer.
@Test func anUnansweredGatewaySaysTheMacMayBeAsleep() {
    let text = AssistantStore.say(URLError(.timedOut))
    #expect(text.hasPrefix(URLError(.timedOut).localizedDescription))
    #expect(text.hasSuffix(" Your Mac may be asleep."))
    #expect(AssistantStore.say(GatewayError.http(status: 502, body: "")).hasSuffix(GatewayReach.asleepHint))
}

@Test func anOfflinePhoneOrAGatewayAnswerSaysNothingAboutSleep() {
    #expect(AssistantStore.say(URLError(.notConnectedToInternet)) == URLError(.notConnectedToInternet).localizedDescription)
    #expect(!AssistantStore.say(GatewayError.unauthorized).contains("asleep"))
    #expect(!AssistantStore.say(GatewayError.http(status: 500, body: "")).contains("asleep"))
}
