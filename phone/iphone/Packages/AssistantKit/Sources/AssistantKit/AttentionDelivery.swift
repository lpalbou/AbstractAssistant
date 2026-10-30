/// A notice can be answered elsewhere while notification permission or the system's delivered
/// list is being read. Check the live feed before and after those suspensions, and undo an
/// enqueue that lost the race with a resolution. `true` means it was posted while still current.
public enum AttentionDelivery {
    @MainActor
    public static func post(isCurrent: () async -> Bool, prepare: () async -> Bool,
                            enqueue: () async throws -> Void, withdraw: () -> Void) async -> Bool {
        guard await isCurrent() else { return false }
        guard await prepare(), await isCurrent() else { return false }
        do { try await enqueue() } catch { return false }
        guard await isCurrent() else { withdraw(); return false }
        return true
    }
}
