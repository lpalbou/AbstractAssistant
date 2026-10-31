/** Artifact storage references are not automatically user attachments. */
export declare const INTERNAL_ARTIFACT_PARTS: Set<string>;
export declare function internalArtifactPart(part: string): boolean;
export declare function displayArtifactPath(path: string): boolean;
export type MessageArtifact = {
    id: string;
    runId: string;
    name?: string;
};
export declare function replayMessageArtifacts(message: {
    artifact_ids?: string[];
    run_id: string;
}, entries: ReadonlyMap<string, Record<string, unknown>>): {
    refs: MessageArtifact[];
    unresolved: boolean;
};
export declare function internalArtifactMetadata(meta: Record<string, unknown>): boolean;
//# sourceMappingURL=artifact_provenance.d.ts.map