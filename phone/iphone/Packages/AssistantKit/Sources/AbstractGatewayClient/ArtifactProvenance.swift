import Foundation

public extension PhoneArtifact {
    /// Reserved upload namespace; filenames and audio MIME types alone carry no intent.
    var isDictationSource: Bool {
        guard let sourcePath else { return false }
        let path = sourcePath.hasPrefix("client:") ? String(sourcePath.dropFirst(7)) : sourcePath
        let parts = path.replacingOccurrences(of: "\\", with: "/").split(separator: "/").map(String.init)
        guard !parts.contains(".."), !path.hasPrefix("/") else { return false }
        let logical = parts.first == "client" ? Array(parts.dropFirst()) : parts
        return isAudio && logical.count >= 3 && logical[0] == "voice" && logical[1] == "dictation"
    }

    /// Apply after collecting all pages: a transcript may precede its source in the listing.
    /// Historical transcription sources without explicit dictation provenance remain visible.
    static func classifyingConversationVoice(_ artifacts: [PhoneArtifact]) -> [PhoneArtifact] {
        let sources = Set(artifacts.filter(\.isDictationSource).map(\.artifactId))
        return artifacts.map { original in
            var item = original
            if item.semanticKind == "transcript", item.producer?["capability_route"]?.stringValue == "audio.transcribe" {
                let refs = item.sourceRefs.filter { $0["role"]?.stringValue == "source_audio" }
                if !refs.isEmpty && refs.allSatisfy({ ref in
                    guard let id = ref["artifact_id"]?.stringValue ?? ref["$artifact"]?.stringValue else { return false }
                    return sources.contains(id)
                }) { item.isConversationVoice = true }
            }
            return item
        }
    }
}

public extension PhoneArtifact {
    /// Older phone dictation/read-aloud artifacts did not record their UI purpose.
    /// Use the conversation's explicit input/output references to protect real files;
    /// only then infer the old, linked session-memory dictation contract and TTS exports.
    static func classifyingConversationVoice(_ artifacts: [PhoneArtifact], explicitFileIDs: Set<String>?) -> [PhoneArtifact] {
        var result = classifyingConversationVoice(artifacts)
        guard let protected = explicitFileIDs else { return result }
        var legacySources: Set<String> = []
        let byID = Dictionary(artifacts.map { ($0.artifactId, $0) }, uniquingKeysWith: { first, _ in first })
        for transcript in artifacts where transcript.semanticKind == "transcript" && transcript.producer?["capability_route"]?.stringValue == "audio.transcribe" {
            for ref in transcript.sourceRefs where ref["role"]?.stringValue == "source_audio" {
                guard let id = ref["artifact_id"]?.stringValue ?? ref["$artifact"]?.stringValue,
                      let source = byID[id], !protected.contains(id), !protected.contains(transcript.artifactId),
                      source.isAudio, source.semanticKind == "attachment", source.sourceOrigin == "upload", source.sourcePath == "client:ask.wav",
                      source.runId == transcript.runId, source.runId.hasPrefix("session_memory_"),
                      ref["run_id"]?.stringValue == source.runId else { continue }
                legacySources.insert(id)
            }
        }
        for index in result.indices {
            let item = result[index]
            if protected.contains(item.artifactId) { result[index].isConversationVoice = false; result[index].inferredConversationVoice = false; continue }
            if legacySources.contains(item.artifactId) { result[index].isConversationVoice = true; result[index].inferredConversationVoice = true }
            if item.isAudio, item.semanticKind == "voice", item.sourceOrigin == "llm_call", item.producer?["capability_route"]?.stringValue == "tts" {
                result[index].isConversationVoice = true; result[index].inferredConversationVoice = true
            }
            if item.semanticKind == "transcript", item.producer?["capability_route"]?.stringValue == "audio.transcribe" {
                let sources = item.sourceRefs.filter { $0["role"]?.stringValue == "source_audio" }
                if !sources.isEmpty && sources.allSatisfy({ ref in
                    guard let id = ref["artifact_id"]?.stringValue ?? ref["$artifact"]?.stringValue else { return false }
                    return legacySources.contains(id) || result.contains { $0.artifactId == id && $0.isDictationSource && !protected.contains(id) }
                }) { result[index].isConversationVoice = true; result[index].inferredConversationVoice = !item.isConversationVoice }
            }
        }
        return result
    }
}
