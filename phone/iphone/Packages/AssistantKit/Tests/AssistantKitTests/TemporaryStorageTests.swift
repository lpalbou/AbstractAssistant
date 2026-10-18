import Foundation
import Testing
import AssistantKit

@Test func staleCopiesAndLegacyRecordingsAreRemovedWithoutTouchingOriginals() throws {
    let base = FileManager.default.temporaryDirectory.appending(path: "storage-test-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: base) }
    let storage = PhoneTemporaryStorage(temporaryDirectory: base)
    for kind in PhoneTemporaryStorage.Kind.allCases {
        let folder = try storage.makeDirectory(for: kind)
        try Data(repeating: 1, count: 1024).write(to: folder.appending(path: "copy"))
    }
    let legacy = ["iphone-voice-\(UUID()).wav", "Photo-\(UUID()).jpg", "phone-import-\(UUID())", "phone-attachment-\(UUID())"]
    for name in legacy { try Data("disposable".utf8).write(to: base.appending(path: name)) }
    let originals = ["holiday.jpg", "Photo-family.jpg", "phone-import-original", "iphone-voice-not-a-uuid.wav", "settings.plist"]
    for name in originals { try Data("original".utf8).write(to: base.appending(path: name)) }
    try storage.removeStaleFiles(); try storage.removeStaleFiles()
    #expect(!FileManager.default.fileExists(atPath: storage.root.path))
    for name in legacy { #expect(!FileManager.default.fileExists(atPath: base.appending(path: name).path)) }
    for name in originals { #expect(try Data(contentsOf: base.appending(path: name)) == Data("original".utf8)) }
}

@Test func discardingOnePreviewRemovesOnlyItsOperationAndNeverAnOriginal() throws {
    let base = FileManager.default.temporaryDirectory.appending(path: "storage-test-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: base) }
    let storage = PhoneTemporaryStorage(temporaryDirectory: base)
    let first = try storage.makeDirectory(for: .previews), second = try storage.makeDirectory(for: .previews)
    let copy = first.appending(path: "photo.jpg"), original = base.appending(path: "photo.jpg")
    try Data("copy".utf8).write(to: copy); try Data("original".utf8).write(to: original)
    try storage.discard(copy)
    #expect(!FileManager.default.fileExists(atPath: first.path))
    #expect(FileManager.default.fileExists(atPath: second.path))
    #expect(throws: CocoaError.self) { try storage.discard(original) }
    #expect(try Data(contentsOf: original) == Data("original".utf8))
}

@Test func cleanupDoesNotFollowSymlinksIntoUserFiles() throws {
    let base = FileManager.default.temporaryDirectory.appending(path: "storage-test-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: base) }
    let original = base.appending(path: "Originals", directoryHint: .isDirectory)
    let temporary = base.appending(path: "Tmp", directoryHint: .isDirectory)
    try FileManager.default.createDirectory(at: original, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
    let saved = original.appending(path: UUID().uuidString)
    try Data("keep me".utf8).write(to: saved)
    let storage = PhoneTemporaryStorage(temporaryDirectory: temporary)
    try FileManager.default.createDirectory(at: storage.root, withIntermediateDirectories: true)
    try FileManager.default.createSymbolicLink(at: storage.root.appending(path: "previews"), withDestinationURL: original)
    #expect(throws: CocoaError.self) { try storage.makeDirectory(for: .previews) }
    #expect(throws: CocoaError.self) { try storage.discard(storage.root.appending(path: "previews/" + saved.lastPathComponent)) }
    try storage.removeStaleFiles()
    #expect(try Data(contentsOf: saved) == Data("keep me".utf8))
}

@Test func launchCleanupRecoversFromADanglingOwnedRootSymlink() throws {
    let base = FileManager.default.temporaryDirectory.appending(path: "storage-test-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: base) }
    let storage = PhoneTemporaryStorage(temporaryDirectory: base)
    try FileManager.default.createSymbolicLink(at: storage.root, withDestinationURL: base.appending(path: "missing"))
    #expect(throws: CocoaError.self) { try storage.makeDirectory(for: .imports) }
    try storage.removeStaleFiles()
    let folder = try storage.makeDirectory(for: .imports)
    #expect(FileManager.default.fileExists(atPath: folder.path))
}
