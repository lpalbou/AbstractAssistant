import React from "react";
import { type AutomationPanelProps, type AutomationTurn } from "@abstractframework/ui-kit";
import { type ChatMessageCardProps } from "./chat_message_card.js";
import { type GatewayFetch } from "./workspace_browser.js";
/** The chat's renderer for automation text (prompts, bodies). */
export declare function renderAutomationText(text: string): React.ReactElement;
/** Speaker shown on each turn's card: the trigger sent the message; the automation answered. */
export declare const AUTOMATION_TURN_TITLES: Record<AutomationTurn["kind"], string>;
/** One occurrence turn as the shared chat card. */
export declare function renderAutomationTurn(turn: AutomationTurn, messageProps?: Omit<ChatMessageCardProps, "message">): React.ReactElement;
/** Spread into `AutomationPanel`: `<AutomationPanel {...automationRenderers} … />`. */
export declare const automationRenderers: {
    renderText: (text: string) => React.ReactElement;
    renderTurn: (turn: AutomationTurn) => React.ReactElement;
};
export type AutomationPanelWithMarkdownProps = Omit<AutomationPanelProps, "renderText" | "renderTurn"> & {
    /**
     * The host's credentialed gateway request. When given (and `onOpenResource`
     * is not), the ledger JSON and artifact links open through it
     * (`openGatewayResource`); without either, the panel shows no such links.
     */
    fetchGateway?: GatewayFetch;
    /** Shared chat affordances, including narration, applied to occurrence turns. */
    messageProps?: Omit<ChatMessageCardProps, "message">;
};
/** `AutomationPanel` with the shared chat rendering already wired. */
export declare function AutomationPanelWithMarkdown(props: AutomationPanelWithMarkdownProps): React.ReactElement;
//# sourceMappingURL=automation_markdown.d.ts.map