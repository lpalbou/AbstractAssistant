import React from "react";
import { type AfDrawerPanel, type VoiceClientPreferences } from "@abstractframework/ui-kit";
import type { ChatMessage, ChatMessageCardProps } from "./chat_message_card.js";
import { type GatewayFetch } from "./workspace_browser.js";
/** Which documentation the assistant answers from. */
export type DocsAssistantSource = {
    /** The corpus id the gateway serves at `docs/corpus?app=<id>`: "gateway"
     * (the console) or an app id ("code", "flow", "observer", "continuum",
     * "entity"). */
    app: string;
    /** Display name, e.g. "AbstractCode". */
    name: string;
};
/** The shipped docs-qa workflow (abstractgateway flows/bundles/docs-qa@0.1.1.flow,
 * the version the gateway's terminal console pins too). Inputs: prompt, docs, app. */
export declare const DOCS_QA_WORKFLOW: {
    readonly registry_scope: "tenant_catalog";
    readonly bundle_id: "docs-qa";
    readonly bundle_version: "0.1.1";
    readonly flow_id: "docsqa001";
};
/** The session purpose the gateway records for a Docs assistant chat
 * (`POST runs/start` `kind`): conversation lists leave it out; the drawer's
 * history lists it (`GET runs?root_only=true&kind=docs`). */
export declare const DOCS_SESSION_KIND: "docs";
export declare function docsCorpusPath(app: string): string;
export declare function newDocsSessionId(app: string): string;
/** An attachment as the gateway returns it from `POST attachments/upload`. */
export type DocsAttachmentRef = {
    $artifact: string;
    [key: string]: unknown;
};
/** The `POST runs/start` body for one question. */
export declare function docsQaStartBody(args: {
    question: string;
    docs: string;
    appName: string;
    sessionId: string;
    attachments?: DocsAttachmentRef[];
}): Record<string, unknown>;
/** The answer of a COMPLETED docs-qa run (`output.response`), or "". */
export declare function docsAnswerFromRun(run: unknown): string;
/** The run's history receipt as one sentence when earlier messages were not replayed. */
export declare function docsReplayNote(history: unknown): string;
/** Parse an SSE body into frames. Ends when the body ends or `signal` aborts. */
export declare function sseFrames(body: ReadableStream<Uint8Array>, signal?: AbortSignal): AsyncGenerator<{
    event: string;
    data: string;
}>;
export type DocsAskContext = {
    signal: AbortSignal;
    sessionId: string;
    files?: File[];
    /** The live reply text so far (streamed runs). */
    onText?: (text: string) => void;
    /** The completed run's history receipt (`session_history`). */
    onHistory?: (history: unknown) => void;
    /** The Gateway run owning this answer and its generated speech. */
    onRun?: (runId: string) => void;
};
export type DocsAsk = (question: string, ctx: DocsAskContext) => Promise<string>;
/**
 * The docs-qa transport: corpus (cached per source on success) → uploads →
 * run start → live deltas + polling → the completed run's answer.
 */
export declare function makeDocsQaAsk(opts: {
    fetchGateway: GatewayFetch;
    source: DocsAssistantSource;
    pollMs?: number;
    timeoutMs?: number;
}): DocsAsk;
/** One past Docs assistant conversation of this app (the drawer's history). */
export type DocsHistoryItem = {
    sessionId: string;
    title: string;
    updatedAt: string;
    runIds: string[];
};
/** `GET runs?root_only=true&kind=docs` for this source's sessions, newest first, titled by their first question. */
export declare function loadDocsHistory(fetchGateway: GatewayFetch, app: string, opts?: {
    signal?: AbortSignal;
    max?: number;
}): Promise<DocsHistoryItem[]>;
/** A past conversation as messages: each turn's question (its input) and answer (the completed run's response). */
export declare function loadDocsConversation(fetchGateway: GatewayFetch, item: DocsHistoryItem, appName: string, signal?: AbortSignal): Promise<ChatMessage[]>;
export type DocsHistoryListProps = {
    items: DocsHistoryItem[];
    state: "loading" | "ready" | "error";
    error?: string;
    nowMs: number;
    activeSessionId?: string;
    onOpen: (item: DocsHistoryItem) => void;
    onArchive: (item: DocsHistoryItem) => void;
};
/** The drawer's history: past conversations (newest first), open or archive (inline confirm). */
export declare function DocsHistoryList(props: DocsHistoryListProps): React.ReactElement;
export type DocsAssistantPanelProps = {
    source: DocsAssistantSource;
    messages: ChatMessage[];
    draft: string;
    onDraftChange: (value: string) => void;
    onSend: () => void;
    onStop?: () => void;
    busy?: boolean;
    /** Composer disabled with this sentence in the thread (e.g. not connected). */
    blockedNotice?: string;
    files?: {
        id: string;
        name: string;
    }[];
    onAddFiles?: (files: File[]) => void;
    onRemoveFile?: (id: string) => void;
    /** Receives a refusal sentence (e.g. a dropped folder). */
    onNotice?: (text: string) => void;
    /** A one-line notice above the composer (drop refusals, replay receipt). */
    notice?: string;
    suggestions?: string[];
    onSuggestion?: (text: string) => void;
    placeholder?: string;
    onSpeakToggle?: ChatMessageCardProps["onSpeakToggle"];
    getSpeakState?: ChatMessageCardProps["getSpeakState"];
};
/** The stateless view (thread, composer, footer); the drawer owns the state. */
export declare function DocsAssistantPanel(props: DocsAssistantPanelProps): React.ReactElement;
/** What the docs assistant needs, wherever it is mounted (drawer or drawer-system panel). */
export type DocsAssistantChatProps = {
    source: DocsAssistantSource;
    /** The host's gateway fetch (relative `api/gateway/...` paths). */
    fetchGateway: GatewayFetch;
    /** False = the composer is disabled with "Connect to the gateway…". */
    connected: boolean;
    suggestions?: string[];
    placeholder?: string;
    /** App voice overrides and playback preferences; absent = Gateway defaults. */
    voicePreferences?: VoiceClientPreferences;
    /** A kept-alive rail host can stop playback when its panel is hidden. */
    visible?: boolean;
    /** Test seam: replaces the docs-qa transport. */
    ask?: DocsAsk;
};
export type DocsAssistantDrawerProps = DocsAssistantChatProps & {
    open: boolean;
    onClose: () => void;
    width?: number;
    topOffset?: number | "auto";
    className?: string;
    /**
     * Move focus into the drawer on open and back on close (the kit AfDrawer's
     * focus handling). Default false: the drawer keeps its pre-0036 behaviour
     * (no soft keyboard on open; apps with their own focus hook are not doubled).
     */
    manageFocus?: boolean;
};
/**
 * The drawer every surface mounts (keep it mounted while closed: the kit's
 * keep-alive contract keeps the conversation and an in-flight answer).
 */
export declare function DocsAssistantDrawer(props: DocsAssistantDrawerProps): React.ReactElement;
/**
 * The docs assistant as the content of an AfDrawerSystem panel: the same
 * conversation as the drawer, its header actions in the panel's header
 * (`AfPanelHeaderActions`). Mount it through `docsAssistantPanel(...)`.
 */
export declare function DocsAssistantPanelContent(props: DocsAssistantChatProps): React.ReactElement;
export type DocsAssistantPanelOptions = Omit<DocsAssistantChatProps, "source" | "fetchGateway"> & {
    /** Panel id (default "docs"). */
    id?: string;
    /** Panel label (default "Docs assistant"). */
    label?: string;
    /** "drawer" (default: opened by the top bar's book button) or "rail" (a rail tab). */
    mode?: "drawer" | "rail";
    side?: "left" | "right";
    defaultWidth?: number;
};
/**
 * The docs assistant as an AfDrawerSystem panel (ADR 0001 §6: an opaque
 * `{id, label, icon, content}`): kept alive ("always") so the conversation and
 * an in-flight answer survive closing. Toggle it with the top bar's `docs`
 * button: `docs={{open: active === "docs", onToggle: () => setActive(a => a === "docs" ? null : "docs")}}`.
 */
export declare function docsAssistantPanel(source: DocsAssistantSource, fetchGateway: GatewayFetch, opts: DocsAssistantPanelOptions): AfDrawerPanel;
export default DocsAssistantDrawer;
//# sourceMappingURL=docs_assistant.d.ts.map