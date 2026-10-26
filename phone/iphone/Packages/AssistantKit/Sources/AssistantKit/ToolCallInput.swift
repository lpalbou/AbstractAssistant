import Foundation
import AbstractGatewayClient

/// Only structured arguments are retained; malformed raw strings are never displayed.
public enum ToolCallInput {
    public static func display(_ value: JSONValue?) -> String? {
        guard var value, value != .null else { return nil }
        if let text = value.stringValue {
            guard let parsed = try? JSONDecoder().decode(JSONValue.self, from: Data(text.utf8)) else { return nil }
            value = parsed
        }
        guard value.objectValue != nil || { if case .array = value { return true }; return false }() else { return nil }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        guard let bytes = try? encoder.encode(redacted(value)), let text = String(data: bytes, encoding: .utf8) else { return nil }
        let marker = "\n[Truncated for display]"
        return text.count > 4000 ? String(text.prefix(4000 - marker.count)) + marker : text
    }
    public static func isCredential(_ key: String) -> Bool {
        let key = key.lowercased().filter { $0.isLetter || $0.isNumber }
        return ["authorization", "proxyauthorization", "password", "passwd", "cookie", "setcookie", "credential", "credentials"].contains(key)
            || key.contains("apikey") || key.contains("privatekey") || key.contains("clientsecret")
            || key.hasSuffix("password") || key.hasSuffix("passwd") || key.contains("secret") || key.hasSuffix("token")
            || key.hasSuffix("accesstoken") || key.hasSuffix("refreshtoken") || key.hasSuffix("idtoken")
            || key.hasSuffix("sessiontoken") || key == "token" || key == "secret" || key.hasSuffix("secretkey")
    }
    private static func redacted(_ value: JSONValue) -> JSONValue {
        switch value {
        case .object(let object): return .object(object.reduce(into: [:]) { result, pair in
            if pair.key.hasPrefix("_") || ["reasoning", "system", "messages"].contains(pair.key.lowercased()) { return }
            result[pair.key] = isCredential(pair.key) ? .string("[Hidden]") : redacted(pair.value)
        })
        case .array(let values): return .array(values.map(redacted))
        default: return value
        }
    }
}
