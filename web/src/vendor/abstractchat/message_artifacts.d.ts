import React from "react";
import { type AfGatewayFetch } from "@abstractframework/ui-kit";
import type { ChatMessage } from "./chat_message_card.js";
import { type MessageArtifact } from "./artifact_provenance.js";
export type { MessageArtifact } from "./artifact_provenance.js";
/** Walk only attachment/output fields selected by the caller, never internal run bookkeeping. */
export declare function messageArtifactRefs(value: unknown, runId: string): MessageArtifact[];
export declare function submittedArtifacts(body: unknown, runId: string): MessageArtifact[];
export declare function outputArtifacts(output: unknown, runId: string): MessageArtifact[];
export declare function useMessageArtifacts(messages: ChatMessage[], fetchGateway: AfGatewayFetch | undefined, scope: string, run?: {
    runId: string;
    output: unknown;
}): {
    messages: ChatMessage[];
    error: string;
    retry: () => void;
};
export declare const ArtifactFetchContext: React.Context<AfGatewayFetch | undefined>;
export declare function MessageArtifactChip({ artifact, }: {
    artifact: MessageArtifact;
}): React.ReactElement;
/** Bound all metadata/input/content reads for one mounted conversation. Aborted queued jobs never fetch. */
export declare function boundedArtifactFetch(fetchGateway: AfGatewayFetch): AfGatewayFetch;
//# sourceMappingURL=message_artifacts.d.ts.map