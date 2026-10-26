import Foundation

public struct EntityDraft: Sendable, Equatable {
    public let name: String
    public init(name: String) { self.name = name.trimmingCharacters(in: .whitespacesAndNewlines) }
    public var slug: String { name.lowercased().replacingOccurrences(of: " ", with: "-") }
    public var valid: Bool { slug.range(of: "^[a-z0-9][a-z0-9_-]{0,63}$", options: .regularExpression) != nil }
    public var body: JSONValue { .object(["name": .string(name), "framework": .bool(true)]) }
}

public struct EntityValidation: Decodable, Sendable {
    public let ok: Bool
    public let errors: [String]
    public let warnings: [String]
    public let exists: Bool
    public let slug: String
    public init(ok: Bool, errors: [String] = [], warnings: [String] = [], exists: Bool = false, slug: String) {
        self.ok = ok; self.errors = errors; self.warnings = warnings; self.exists = exists; self.slug = slug
    }
}

public struct CreatedEntity: Sendable {
    public let entity: EntitySummary
    public let created: Bool
    public let warnings: [String]
    public init(_ value: JSONValue) throws {
        guard let slug = value["manifest"]?["slug"]?.stringValue, EntityDraft(name: slug).valid,
              let name = value["manifest"]?["name"]?.stringValue, !name.isEmpty,
              case .bool(let created)? = value["created"] else { throw GatewayError.invalidResponse }
        self.created = created
        entity = EntitySummary(name: slug, extra: ["display_name": .string(name)])
        var notes: [String] = []
        if case .array(let rows)? = value["warnings"] { notes += rows.compactMap(\.stringValue) }
        for key in ["skills_warning", "capability_map_warning"] { if let note = value[key]?.stringValue { notes.append(note) } }
        warnings = notes
    }
}

public extension EntitySummary {
    var displayName: String { extra["display_name"]?.stringValue ?? name.replacingOccurrences(of: "-", with: " ").capitalized }
}

public extension GatewayClient {
    func validateEntity(_ draft: EntityDraft) async throws -> EntityValidation { throw PhoneAttachmentError.unsupported }
    func createEntity(_ draft: EntityDraft) async throws -> CreatedEntity { throw PhoneAttachmentError.unsupported }
}
