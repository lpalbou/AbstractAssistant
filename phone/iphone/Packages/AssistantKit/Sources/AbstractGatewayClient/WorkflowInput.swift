import Foundation

/// Named inputs advertised by a runnable workflow. The Gateway remains the schema authority.
public struct WorkflowInput: Sendable, Equatable, Identifiable {
    public var id: String
    public var label: String
    public var type: String
    public var required: Bool
    public var description: String?
    public var allowsNull: Bool
    public var choices: [JSONValue]?
    public init(id: String, label: String, type: String, required: Bool, description: String? = nil, choices: [JSONValue]? = nil, allowsNull: Bool = false) {
        self.id = id; self.label = label; self.type = type; self.required = required; self.description = description; self.choices = choices; self.allowsNull = allowsNull
    }
    public static func type(in schema: JSONValue, fallback: String = "unknown") -> String {
        let declared = schema["type"]?.stringValue ?? schema["type"]?.arrayValue?.compactMap(\.stringValue).first(where: { $0 != "null" })
        if let declared, ["string", "integer", "number", "boolean", "object", "array"].contains(declared) { return declared }
        if schema["anyOf"] != nil || schema["oneOf"] != nil { return "json" }
        switch (declared ?? fallback).lowercased() {
        case "text", "path", "file", "directory", "workspace_file", "workspace_folder", "provider", "model": return "string"
        case "double": return "number"
        case "map": return "object"
        case "string", "integer", "int", "number", "float", "boolean", "bool", "object", "dict", "array", "list": return (declared ?? fallback).lowercased()
        default: return "json"
        }
    }
    public static func nullable(_ schema: JSONValue) -> Bool {
        schema["type"] == .string("null") || schema["type"]?.arrayValue?.contains(.string("null")) == true ||
        (schema["anyOf"]?.arrayValue ?? schema["oneOf"]?.arrayValue ?? []).contains(where: nullable)
    }
    public static func text(_ value: JSONValue) -> String {
        if case .string(let text) = value { return text }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return (try? String(data: encoder.encode(value), encoding: .utf8)) ?? ""
    }
    public func value(from text: String) throws -> JSONValue {
        if let choices, let selected = choices.first(where: { Self.text($0) == text }) { return selected }
        let value: JSONValue
        if ["string", "text"].contains(type) { value = .string(text) }
        else {
            guard let parsed = try? JSONDecoder().decode(JSONValue.self, from: Data(text.utf8)) else { throw WorkflowInputError(message: "Enter a valid \(type) for \(label).") }
            if parsed == .null && allowsNull { return parsed }
            let valid: Bool
            switch (type, parsed) {
            case ("boolean", .bool), ("bool", .bool), ("number", .number), ("float", .number), ("object", .object), ("dict", .object), ("array", .array), ("list", .array): valid = true
            case ("integer", .number(let number)), ("int", .number(let number)): valid = number.rounded() == number
            case ("unknown", _), ("any", _), ("json", _): valid = true
            default: valid = false
            }
            guard valid else { throw WorkflowInputError(message: "Enter a valid \(type) for \(label).") }
            value = parsed
        }
        if let choices, !choices.contains(value) { throw WorkflowInputError(message: "Choose an available value for \(label).") }
        return value
    }
}
public struct WorkflowInputError: LocalizedError, Sendable {
    public var message: String
    public var errorDescription: String? { message }
}
