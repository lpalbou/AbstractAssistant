import React from "react";
import { type AfGatewayFetch } from "@abstractframework/ui-kit";
import type { ChatMessage } from "./chat_message_card.js";
export type MessageArtifact = {
    id: string;
    runId: string;
    name?: string;
};
/** Walk only attachment/output fields selected by the caller, never internal run bookkeeping. */
export declare function messageArtifactRefs(value: unknown, runId: string): MessageArtifact[];
export declare function submittedArtifacts(body: unknown, runId: string): MessageArtifact[];
export declare function outputArtifacts(output: unknown, runId: string): MessageArtifact[];
export declare function useMessageArtifacts(messages: ChatMessage[], fetchGateway: AfGatewayFetch | undefined, scope: string, run?: {
    runId: string;
    output: unknown;
}): {
    messages: (ChatMessage | {
        artifactRefs: {
            id: string;
            runId: string;
        }[];
        id?: string;
        role: string;
        content: string;
        ts?: string;
        title?: string;
        level?: import("./chat_message_card.js").ChatMessageLevel;
        kind?: string;
        toolActivity?: import("./workflow_evidence.js").WorkflowToolActivity;
        statistics?: import("./workflow_evidence.js").WorkflowStatistics;
        runId?: string;
        live?: import("./chat_message_card.js").ChatLiveReply;
        reasoning?: string;
        media?: import("./chat_message_card.js").ChatMedia[];
        stats?: import("./chat_message_card.js").ChatStat[];
        attachments?: import("./chat_message_card.js").ChatAttachment[];
        artifactIds?: string[];
    })[];
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