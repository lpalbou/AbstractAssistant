import Foundation
import Testing
@testable import AbstractGatewayClient

@Test func speechEventsDecodeTheirTextSegment() throws {
    let text = "Bonjour ! Il est 14 h 30 👍🏽. Déjà fini ?"
    let audio = #"{"type":"audio","sequence":3,"segment":1,"text_start":29,"text_end":40,"audio_b64":"UklGRg=="}"#
    let ev = try JSONDecoder().decode(SpeechEvent.self, from: Data(audio.utf8))
    #expect(ev.type == "audio" && ev.segment == 1 && ev.textStart == 29 && ev.textEnd == 40)
    let end = try JSONDecoder().decode(SpeechEvent.self, from: Data(
        #"{"type":"segment_end","schema":"abstractvoice.tts_stream.segment_end.v1","segment":0,"text_start":0,"text_end":28}"#.utf8))
    #expect(end.type == "segment_end" && end.segment == 0 && end.textEnd == 28)
    // The offsets count Unicode scalars: the 👍🏽 is two of them.
    let scalars = Array(text.unicodeScalars)
    #expect(String(String.UnicodeScalarView(scalars[0..<28])) == "Bonjour ! Il est 14 h 30 👍🏽.")
    #expect(String(String.UnicodeScalarView(scalars[29...])) == "Déjà fini ?")
    // An engine that reports no segments: the fields are absent, the line still decodes.
    let plain = try JSONDecoder().decode(SpeechEvent.self, from: Data(#"{"type":"audio","sequence":0,"audio_b64":"UklGRg=="}"#.utf8))
    #expect(plain.segment == nil && plain.textStart == nil && plain.textEnd == nil)
}
