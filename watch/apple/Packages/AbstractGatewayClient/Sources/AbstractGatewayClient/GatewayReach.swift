import Foundation

/// When the gateway cannot be reached at all, the computer it runs on may simply be asleep. The
/// gateway keeps its Mac awake while remote access is on, but a Mac put to sleep on purpose (Apple
/// menu, the lid, the power button) stays asleep. The watch and the iPhone then add one plain line,
/// `asleepHint`, under their "can't reach" message.
///
/// One rule for every Apple client, decided on error TYPES only, never on message text.
public enum GatewayReach {
    public static let asleepHint = "Your Mac may be asleep."

    /// True when the gateway's computer did not answer: a network error other than this device being
    /// offline or a cancelled request, no HTTP answer at all, or a proxy in front of the gateway
    /// (Tailscale Funnel, a reverse proxy) answering that the gateway behind it is down (502, 504).
    /// False for every answer the gateway itself gave (signed out, refused, a server error).
    public static func mayBeAsleep(_ error: Error) -> Bool {
        if let e = error as? URLError {
            return ![.notConnectedToInternet, .dataNotAllowed, .internationalRoamingOff, .callIsActive, .cancelled].contains(e.code)
        }
        if let e = error as? GatewayError {
            switch e {
            case .invalidResponse: return true
            case .http(let status, _): return status == 502 || status == 504
            default: return false
            }
        }
        if case .unreachable? = error as? GatewaySignIn.Failure { return true }
        return false
    }
}
