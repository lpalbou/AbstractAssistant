import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func sessionTitlesOnThePhoneAreCutNear32Characters() {
    #expect(SessionSummary.title(fromPrompt: "Did the QC pass?\nmore", limit: 32) == "Did the QC pass?")
    let t = SessionSummary.title(fromPrompt: "Compare overall survival by treatment arm in the ADTTE dataset I sent you this morning", limit: 32)
    #expect(t.hasSuffix("…") && t.count <= 45 && !t.contains("this morning"))
}

