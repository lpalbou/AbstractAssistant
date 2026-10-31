import React from "react";
import type { AfDrawerPanel, IconName } from "@abstractframework/ui-kit";
import type { ChatMessage } from "./chat_message_card.js";
export type AssistantAskContext = {
    signal: AbortSignal;
    history: ChatMessage[];
};
export type AssistantAsk = (question: string, ctx: AssistantAskContext) => Promise<string> | AsyncIterable<string>;
export type AssistantPanelProps = {
    /** The injected transport. */
    ask: AssistantAsk;
    /** Assistant display name (message header). Default "Assistant". */
    assistantName?: string;
    /** Empty-state copy. Default explains the docs grounding. */
    emptyState?: React.ReactNode;
    /** Suggested first questions rendered in the empty state. */
    suggestions?: string[];
    /** When set, the composer is disabled and this notice renders in-thread
     * (e.g. "Connect to the gateway to use the assistant"). */
    blockedNotice?: string;
    placeholder?: string;
    className?: string;
    /** Controlled history (optional). Uncontrolled by default. */
    messages?: ChatMessage[];
    onMessagesChange?: (next: ChatMessage[]) => void;
};
export declare function AssistantPanel(props: AssistantPanelProps): React.ReactElement;
export type AssistantDrawerPanelOptions = AssistantPanelProps & {
    /** Panel id (default "assistant"). */
    id?: string;
    /** Panel label (default `assistantName`, else "Assistant"). */
    label?: string;
    /** Default "sparkle" (the top bar's assistant icon). */
    icon?: IconName;
    /** "drawer" (default: opened by the top bar's assistant button) or "rail". */
    mode?: "drawer" | "rail";
    side?: "left" | "right";
    defaultWidth?: number;
};
/**
 * An app assistant (e.g. Continuum's advisor) as an AfDrawerSystem panel
 * (ADR 0001 §6: an opaque `{id, label, icon, content}`), kept alive so the
 * conversation survives closing. Toggle it with the top bar's `assistant` button.
 */
export declare function assistantDrawerPanel(opts: AssistantDrawerPanelOptions): AfDrawerPanel;
export default AssistantPanel;
//# sourceMappingURL=assistant_panel.d.ts.map