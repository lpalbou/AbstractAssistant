import Foundation

// An entity's digital identity as the gateway serves it (framework ADR 0052, backlog 1119): one
// record per entity, in its home, reached by reference. The apps draw the entity from the record
// (its design's `watch_code` and its colour) and never from a setting of their own; its voice is
// the gateway's to apply on the entity's speech lane.

/// Who spoke or wrote: `{of, rev}` (`entity:castor@h1#3` as a string). `of` is the entity's
/// `entity_id`; `rev` is the identity's revision at that moment. A reference is never made up: a
/// row without one has none.
public struct IdentityRef: Codable, Hashable, Sendable, CustomStringConvertible {
    public let of: String
    public let rev: Int
    public init?(of: String, rev: Int) {
        guard !of.isEmpty, rev >= 1 else { return nil }
        self.of = of; self.rev = rev
    }
    /// The string form the gateway sends in `X-Identity-Ref`: `<subject>#<rev>`.
    public init?(header: String) {
        guard let mark = header.lastIndex(of: "#"), let rev = Int(header[header.index(after: mark)...]) else { return nil }
        self.init(of: String(header[..<mark]), rev: rev)
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        guard let ref = Self(of: try c.decode(String.self, forKey: .of), rev: try c.decode(Int.self, forKey: .rev)) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "an identity reference needs a subject and a revision of 1 or more"))
        }
        self = ref
    }
    public var description: String { "\(of)#\(rev)" }
    private enum CodingKeys: String, CodingKey { case of, rev }
}

/// What an entity's design draws on the watch (abstractavatar's `watch_code`): one of the watch's
/// orb designs by its letter code (`B`, `AU`), or a silhouette (`shape:kitty`).
public enum WatchDrawing: Hashable, Sendable {
    case design(String)
    case shape(String)
    public init?(watchCode: String?) {
        guard let code = watchCode, !code.isEmpty else { return nil }
        if code.hasPrefix("shape:") {
            let shape = String(code.dropFirst("shape:".count))
            guard !shape.isEmpty else { return nil }
            self = .shape(shape)
        } else { self = .design(code) }
    }
}

/// The identity record (`identity` on `GET /entities/{name}/identity` and on the entity's list row):
/// what the apps read of it. Its voice is applied by the gateway, so the apps do not read it.
public struct EntityIdentity: Decodable, Hashable, Sendable {
    public struct Avatar: Decodable, Hashable, Sendable {
        /// The abstractavatar design id (`watch-vortex`).
        public let style: String
        /// `#rrggbb`.
        public let color: String
        /// The design's watch code, or nil when this gateway's catalog has none for it.
        public let watchCode: String?
        public var drawing: WatchDrawing? { WatchDrawing(watchCode: watchCode) }
        /// The colour as 0…1 components; nil when it is not `#rrggbb`.
        public var rgb: (red: Double, green: Double, blue: Double)? {
            guard color.count == 7, color.first == "#", let v = UInt32(color.dropFirst(), radix: 16) else { return nil }
            return (Double(v >> 16 & 0xff) / 255, Double(v >> 8 & 0xff) / 255, Double(v & 0xff) / 255)
        }
        public init(style: String, color: String, watchCode: String?) { self.style = style; self.color = color; self.watchCode = watchCode }
        private enum CodingKeys: String, CodingKey { case style, color, watchCode = "watch_code" }
    }
    public let rev: Int
    public let avatar: Avatar
    public init(rev: Int, avatar: Avatar) { self.rev = rev; self.avatar = avatar }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        rev = try c.decode(Int.self, forKey: .rev)
        avatar = try c.decode(Avatar.self, forKey: .avatar)
        guard rev >= 1 else { throw DecodingError.dataCorruptedError(forKey: .rev, in: c, debugDescription: "rev starts at 1") }
    }
    private enum CodingKeys: String, CodingKey { case rev, avatar }
}

/// `GET /api/gateway/entities/{name}/identity[?rev=N]`: the record and the reference to it.
public struct EntityIdentityView: Decodable, Hashable, Sendable {
    public let entityId: String
    public let identity: EntityIdentity
    public let identityRef: IdentityRef
    public init(entityId: String, identity: EntityIdentity, identityRef: IdentityRef) {
        self.entityId = entityId; self.identity = identity; self.identityRef = identityRef
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityId = try c.decode(String.self, forKey: .entityId)
        identity = try c.decode(EntityIdentity.self, forKey: .identity)
        identityRef = try c.decode(IdentityRef.self, forKey: .identityRef)
        // The reference names this record: anything else is not the identity asked for.
        guard identityRef.of == entityId, identityRef.rev == identity.rev else {
            throw DecodingError.dataCorruptedError(forKey: .identityRef, in: c, debugDescription: "the reference does not name this record")
        }
    }
    private enum CodingKeys: String, CodingKey { case entityId = "entity_id", identity, identityRef = "identity_ref" }
}

public extension EntitySummary {
    /// The entity's `entity_id` (the subject of its identity references).
    var entityId: String? { extra["entity_id"]?.stringValue }
    /// The identity record on the list row (gateway 0.20); nil when the row has none (a home not
    /// recorded yet, or closed for maintenance) or it is not a record.
    var identity: EntityIdentity? { extra["identity"].flatMap { try? JSONDecoder().decode(EntityIdentity.self, from: JSONEncoder().encode($0)) } }
    /// The reference to the record on the row.
    var identityRef: IdentityRef? { entityId.flatMap { id in identity.flatMap { IdentityRef(of: id, rev: $0.rev) } } }
}

/// Who to name over a line of a conversation: the newest reference, when it differs from the one
/// before it (lines without a reference are skipped). Nil for the first speaker and while the same
/// identity goes on speaking.
public enum SpeakerChange {
    public static func label(_ refs: [IdentityRef?]) -> IdentityRef? {
        let known = refs.compactMap { $0 }
        guard known.count >= 2, let last = known.last, last != known[known.count - 2] else { return nil }
        return last
    }
}

public extension SpeechScope {
    /// The voice a reading asks for: the person's choice for the Assistant's text; none for an
    /// entity's, which the gateway speaks with the entity's own identity voice (a voice named in
    /// the request would replace it).
    func requestedVoice(_ chosen: VoiceChoice?) -> VoiceChoice? {
        if case .run = self { return chosen }
        return nil
    }
}

public extension GatewayError {
    /// A refusal the gateway explained (a 4xx answer with its sentence), as that sentence; nil for
    /// anything else (a failure another try may fix, a sign-in, an answer without a sentence).
    static func refusal(_ error: Error) -> String? {
        guard case GatewayError.http(let status, let body) = error, (400..<500).contains(status),
              ![401, 408, 429].contains(status) else { return nil }
        return GatewaySignIn.detail(Data(body.utf8))
    }
}

public extension GatewayClient {
    func entityIdentity(name: String, rev: Int?) async throws -> EntityIdentityView { throw GatewayError.invalidResponse }
}
