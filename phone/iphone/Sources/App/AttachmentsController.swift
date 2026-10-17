import Foundation
import Observation
import UniformTypeIdentifiers
import AbstractGatewayClient

@MainActor @Observable final class AttachmentsController {
    private(set) var pending: [PhoneArtifact] = []
    private(set) var files: [PhoneArtifact] = []
    private(set) var busy = false
    private(set) var status = ""
    var error: String?
    var preview: URL?
    @ObservationIgnored var onUnauthorized: (() -> Void)?
    @ObservationIgnored private var task: Task<Void, Never>?
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var binding: String?
    @ObservationIgnored private var temporary: [URL] = []
    deinit { for url in temporary { try? FileManager.default.removeItem(at: url) } }
    func bind(_ key: String) { if binding != key { reset(); binding = key } }
    func remove(_ item: PhoneArtifact) { pending.removeAll { $0.id == item.id } }
    func sent() { pending = [] }
    func reset() {
        generation += 1; task?.cancel(); task = nil; busy = false; status = ""; pending = []; files = []; error = nil; preview = nil
        for file in temporary { try? FileManager.default.removeItem(at: file) }; temporary = []
    }
    func cancel() { generation += 1; task?.cancel(); task = nil; busy = false; status = "" }
    func importFile(_ url: URL, client: any GatewayClient, sessionId: String, owned: Bool = false) {
        guard !busy else { if owned { ImportedMedia.remove(url) }; return }
        let epoch = generation; busy = true; status = "Uploading attachment…"; error = nil
        task = Task {
            defer { if owned { ImportedMedia.remove(url) }; if epoch == generation { busy = false; status = "" } }
            do {
                let data = try await Task.detached(priority: .userInitiated) {
                    let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
                    let values = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
                    guard values.isRegularFile == true, (values.fileSize ?? Int.max) <= PhoneArtifact.byteLimit else { throw PhoneAttachmentError.tooLarge }
                    let data = try Data(contentsOf: url); guard data.count <= PhoneArtifact.byteLimit else { throw PhoneAttachmentError.tooLarge }; return data
                }.value
                try Task.checkCancellation(); guard epoch == generation else { return }
                let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
                let artifact = try await client.upload(data: data, filename: url.lastPathComponent, contentType: mime, sessionId: sessionId)
                try Task.checkCancellation(); guard epoch == generation else { return }
                pending.append(artifact)
            } catch { if epoch == generation && !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } } }
        }
    }
    func refresh(client: any GatewayClient, sessionId: String) async {
        let epoch = generation
        do { let items = try await client.artifacts(sessionId: sessionId); guard epoch == generation else { return }; files = items }
        catch { if epoch == generation && !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } } }
    }
    func open(_ file: PhoneArtifact, client: any GatewayClient) {
        guard !busy else { return }; let epoch = generation; busy = true; status = "Downloading attachment…"; error = nil
        task = Task {
            defer { if epoch == generation { busy = false; status = "" } }
            do {
                let data = try await client.download(file); try Task.checkCancellation(); guard epoch == generation else { return }
                let folder = FileManager.default.temporaryDirectory.appending(path: "phone-attachment-" + UUID().uuidString, directoryHint: .isDirectory)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                temporary.append(folder)
                let url = folder.appending(path: PhoneArtifact.safeFilename(file.filename)); try data.write(to: url, options: .atomic); preview = url
            } catch { if epoch == generation && !(error is CancellationError) { self.error = error.localizedDescription; if error as? GatewayError == .unauthorized { onUnauthorized?() } } }
        }
    }
}
