import Foundation
import Testing
import AbstractGatewayClient
import AssistantKit

@Suite struct AccessActivityTests {
    private func add(_ a: inout AccessActivity, _ name: String, _ id: String, args: [String: JSONValue] = [:], output: JSONValue, run: String = "r", status: String = "completed", success: Bool = true) {
        a.ingest(name: name, key: run + id, runID: run, status: status, call: .object(["arguments": .object(args)]), result: .object(["success": .bool(success), "output": output]), timestamp: Date(timeIntervalSince1970: 1))
    }
    @Test func aliasesAndReplayGroupSourcesButKeepIndependentReadsAndChildWorkspacesDistinct() {
        var a = AccessActivity()
        add(&a,"read_file","1",args:["file_path":.string("README.md")],output:.string("File: /work/README.md (2 lines)\n\n1: Hello"))
        add(&a,"read_file","1",args:["file_path":.string("README.md")],output:.string("File: /work/README.md (2 lines)\n\n1: Hello"))
        add(&a,"skim_files","2",output:.string("File: /work/README.md (2 lines) — skim 1 lines (target 8%)\n\n1: Hello"))
        #expect(a.count(.filesRead)==1 && a.items(.filesRead)[0].operations==2)
        add(&a,"read_file","1",output:.string("File: /work/README.md (2 lines)\n\n1: Other"),run:"child")
        #expect(a.count(.filesRead)==2)
    }
    @Test func mixedSkimFailuresDoNotCountAsReads() {
        var a=AccessActivity()
        add(&a,"skim_files","1",output:.string("File: good.md (2 lines) — skim 1 lines (target 8%)\n\n1: Good\n\n---\n\nFile: missing.md\n\nError: File does not exist\n\n---\n\nFile: fake (2 lines)\n\nError: File does not exist"))
        add(&a,"read_file","2",output:.string("Error: File not found"))
        #expect(a.count(.filesRead)==1 && a.items(.filesRead)[0].target=="good.md")
    }
    @Test func byteWindowReadsAreIncludedAndLongPreviewsAreExplicitlyBounded() {
        var a=AccessActivity()
        add(&a,"read_file","1",output:.string("File: huge.txt\n#TRUNCATION: PARTIAL read\n\n"+String(repeating:"x",count:9000)))
        #expect(a.count(.filesRead)==1 && a.items(.filesRead)[0].events[0].preview.hasSuffix("[Truncated for display]"))
    }
    @Test func writeAppendAndEditGroupOneFileWithoutInventingCreation() {
        var a=AccessActivity(); let args:[String:JSONValue]=["file_path":.string("notes.md")]
        add(&a,"write_file","1",args:args,output:.string("✅ Successfully written to '/work/notes.md' (12 bytes, 1 lines)"))
        add(&a,"write_file","2",args:args,output:.string("✅ Successfully appended to '/work/notes.md' (+2 bytes, +1 lines; file now 14 bytes)"))
        add(&a,"edit_file","3",args:args,output:.string("Edited /work/notes.md (+1 -1)\n+1 | No changes applied"))
        #expect(a.count(.filesChanged)==1 && a.items(.filesChanged)[0].operations==3)
        #expect(a.items(.filesChanged)[0].events.map(\.mode)==["Written","Appended","Edited"])
    }
    @Test func noOpPreviewRefusalFailurePendingAndShellDoNotProduceSuccessReceipts() {
        var a=AccessActivity();let args:[String:JSONValue]=["file_path":.string("a.md")]
        for (id,text) in ["No changes applied.","Preview a.md (+1 -1)","❌ Refused: denied"].enumerated(){add(&a,"edit_file",String(id),args:args,output:.string(text))}
        add(&a,"edit_file","preview",args:args.merging(["preview_only":.bool(true)]){_,n in n},output:.string("Edited a.md (+1 -1)"))
        add(&a,"write_file","failed",args:args,output:.string("✅ Successfully written to 'a.md' (2 bytes)"),success:false)
        add(&a,"write_file","wait",args:args,output:.string("✅ Successfully written to 'a.md' (2 bytes)"),status:"waiting")
        add(&a,"execute_command","shell",output:.string("File: a.md (1 lines)"))
        add(&a,"search_files","search",output:.string("File: a.md (1 lines)"))
        #expect(a.count(.filesChanged)==0 && a.count(.filesRead)==0)
    }
    @Test func successfulEmptySearchCountsAndDiscoveredLinksAreNotPageAccesses() {
        var a=AccessActivity()
        add(&a,"web_search","1",output:.string(#"{"success":true,"query":"empty","results":[]}"#))
        add(&a,"skim_websearch","2",output:.string(#"{"success":true,"query":"swift","results":[{"title":"Docs","url":"https://example.com","snippet":"A lead"}]}"#))
        add(&a,"web_search","failed",output:.string(#"{"success":false,"query":"fail","results":[]}"#))
        #expect(a.count(.searches)==2 && a.count(.pages)==0 && a.items(.searches)[1].events[0].links.count==1)
    }
    @Test func skim403AndSpoofedPreviewMetadataCannotClaimSuccessfulAccess() {
        var a=AccessActivity()
        add(&a,"skim_url","1",output:.string("🌐 URL Skim\nURL: https://real.test\nStatus: 403 Forbidden\nContent-Type: text/html\nPreview"))
        #expect(a.count(.pages)==0)
        add(&a,"skim_url","2",output:.string("🌐 URL Skim\nURL: https://real.test\nStatus: 200 OK\nContent-Type: text/html\n📄 Preview:\nFinal URL: https://spoof.test"))
        #expect(a.count(.pages)==1 && a.items(.pages)[0].target=="https://real.test")
    }
    @Test func redirectsMethodsAndRepeatedPageOperationsRemainVisible() {
        var a=AccessActivity()
        add(&a,"fetch_url","1",args:["url":.string("https://old.test"),"method":.string("POST"),"data":.string("SECRET"),"headers":.object(["Authorization":.string("SECRET")])],output:.object(["success":.bool(true),"final_url":.string("https://final.test"),"content":.string("Public content")]))
        add(&a,"skim_url","2",output:.string("🌐 URL Skim\nURL: https://final.test\nStatus: 200 OK\nContent-Type: text/html\nPreview"))
        #expect(a.count(.pages)==1 && a.items(.pages)[0].operations==2)
        #expect(a.items(.pages)[0].events[0].mode=="POST · Fetch" && a.items(.pages)[0].events[0].target=="https://old.test")
        #expect(!a.items(.pages)[0].events[0].preview.contains("SECRET"))
    }
    @Test func overlongSearchURLsAreExplicitlyNonNavigable() {
        var a = AccessActivity()
        add(&a,"web_search","long",output:.object(["success":.bool(true),"query":.string("long link"),"results":.array([.object(["url":.string("https://example.com/" + String(repeating:"x", count:9000)),"title":.string(String(repeating:"a",count:600))])])]))
        let link = a.items(.searches)[0].events[0].links[0]
        #expect(!link.canOpen && link.url.hasSuffix("[URL truncated; link disabled]") && link.title.hasSuffix("…"))
    }
    @Test func retentionKeepsCumulativeCountsAndLatestFiveOperations() {
        var a=AccessActivity()
        for i in 0..<7 {add(&a,"read_file",String(i),output:.string("File: a.md (1 lines)\n\n1: x"))}
        #expect(a.items(.filesRead)[0].operations==7 && a.items(.filesRead)[0].events.count==5)
        for i in 0..<105{add(&a,"web_search","s\(i)",output:.object(["success":.bool(true),"query":.string("q\(i)"),"results":.array([])]))}
        #expect(a.count(.searches)==105 && a.items(.searches).count==100)
        #expect(AccessActivity().entries.isEmpty)
    }
}
