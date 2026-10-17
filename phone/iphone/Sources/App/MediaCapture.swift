import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import CoreTransferable
import AbstractGatewayClient

struct ImportedMedia: Transferable, Sendable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .data) { received in ImportedMedia(url: try copy(received.file)) }
    }
    static func remove(_ url: URL) {
        let parent = url.deletingLastPathComponent()
        if parent.lastPathComponent.hasPrefix("phone-import-") { try? FileManager.default.removeItem(at: parent) }
        else { try? FileManager.default.removeItem(at: url) }
    }
    static func copy(_ source: URL) throws -> URL {
        let size = try source.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max
        guard size <= PhoneArtifact.byteLimit else { throw PhoneAttachmentError.tooLarge }
        let folder = FileManager.default.temporaryDirectory.appending(path: "phone-import-" + UUID().uuidString, directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let destination = folder.appending(path: PhoneArtifact.safeFilename(source.lastPathComponent))
        try FileManager.default.copyItem(at: source, to: destination); return destination
    }
}

struct CameraCapture: UIViewControllerRepresentable {
    let video: Bool
    var onResult: (Result<URL, Error>) -> Void
    @Environment(\.dismiss) private var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController(); picker.sourceType = .camera
        picker.mediaTypes = [video ? UTType.movie.identifier : UTType.image.identifier]
        if video { picker.cameraCaptureMode = .video; picker.videoMaximumDuration = 30; picker.videoQuality = .typeMedium }
        picker.delegate = context.coordinator; return picker
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
    @MainActor final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        var parent: CameraCapture
        init(_ parent: CameraCapture) { self.parent = parent }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            do {
                let url: URL
                if let source = info[.mediaURL] as? URL { url = try ImportedMedia.copy(source) }
                else if let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.85) {
                    guard data.count <= PhoneArtifact.byteLimit else { throw PhoneAttachmentError.tooLarge }
                    url = FileManager.default.temporaryDirectory.appending(path: "Photo-" + UUID().uuidString + ".jpg"); try data.write(to: url)
                } else { throw GatewayError.invalidResponse }
                parent.onResult(.success(url))
            } catch { parent.onResult(.failure(error)) }
            parent.dismiss()
        }
    }
}
