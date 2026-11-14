import Foundation

/// When the gateway cannot be reached at all, the computer it runs on may simply be asleep. The
/// gateway keeps its Mac awake while remote access is on, but a Mac put to sleep on purpose (Apple
/// menu, the lid, the power button) stays asleep. The watch and the iPhone then add one plain line,
/// `asleepHint`, under their "can't reach" message.
///
/// One rule for every Apple client, decided on error TYPES only, never on message text.
public enum GatewayReach {
    public static let asleepHint = "Your Mac may be asleep."

    /// A connectivity failure can mean the gateway host is asleep. Configuration,
    /// certificate, decoding and this-device-offline errors are not evidence of sleep.
    public static func mayBeAsleep(_ error: Error) -> Bool {
        if let e = error as? URLError {
            return [.timedOut, .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed, .networkConnectionLost].contains(e.code)
        }
        if case .http(let status, _)? = error as? GatewayError { return status == 502 || status == 504 }
        // Sign-in's generic unreachable failure does not retain a typed cause.
        return false
    }
}
