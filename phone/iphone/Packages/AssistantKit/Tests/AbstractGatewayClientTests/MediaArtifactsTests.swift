import Foundation
import Testing
import AbstractGatewayClient

@Suite struct MediaArtifactsTests {
    private func run(_ output: String) throws -> RunSummary {
        try JSONDecoder().decode(RunSummary.self, from: Data((#"{"run_id":"root","status":"completed","output":SIG}"#.replacingOccurrences(of: "SIG", with: output)).utf8))
    }
    @Test func realGeneratedImageAliasesDeduplicateAndInferFilename() throws {
        let result = try run(#"{"response":"Here","artifact":{"$artifact":"image","run_id":"root","content_type":"image/png"},"image_artifact":{"$artifact":"image","run_id":"root","content_type":"image/png"},"outputs":{"image":[{"artifact_id":"image","content_type":"image/png","artifact_ref":{"$artifact":"image","run_id":"root"}}]}}"#)
        #expect(result.mediaArtifacts.count == 1)
        #expect(result.mediaArtifacts.first?.filename == "Image-image.png")
        #expect(result.mediaArtifacts.first?.isImage == true)
    }
    @Test func bareAliasIsEnrichedByTypedOutputInsteadOfHidingPreview() throws {
        let result = try run(#"{"artifact":{"$artifact":"image","run_id":"root"},"outputs":{"image":[{"artifact_id":"image","content_type":"image/png","artifact_ref":{"$artifact":"image","run_id":"root"}}]}}"#)
        #expect(result.mediaArtifacts.count == 1)
        #expect(result.mediaArtifacts.first?.isImage == true)
        #expect(result.mediaArtifacts.first?.filename.hasSuffix(".png") == true)
    }
    @Test func nestedReferenceOwnerWinsOverOutputWrapperRootFallback() throws {
        let result = try run(#"{"outputs":{"image":[{"artifact_id":"image","content_type":"image/png","artifact_ref":{"$artifact":"image","run_id":"child"}}]}}"#)
        #expect(result.mediaArtifacts.map(\.id) == ["child:image"])
        #expect(result.mediaArtifacts.first?.isImage == true)
    }
    @Test func soundOutputAndVoiceAliasArePublicButReasoningAndURLsAreNot() throws {
        let result = try run(#"{"audio_artifact":null,"outputs":{"music":[{"content_type":"audio/wav","artifact_ref":{"$artifact":"sound","run_id":"root"}}]},"reasoning":{"artifact":{"$artifact":"private","run_id":"root"}},"response":"https://untrusted.invalid/private.png"}"#)
        #expect(result.mediaArtifacts.map(\.id) == ["root:sound"])
        #expect(result.mediaArtifacts.first?.filename == "Audio-sound.wav")
        #expect(result.mediaArtifacts.first?.isAudio == true)
    }
    @Test func previewNamesCannotEscapeTheirDirectory() {
        let file = PhoneArtifact(artifactId: "image", runId: "root", filename: "../../outside", contentType: "image/png")
        #expect(file.filename == "outside.png")
    }
}
