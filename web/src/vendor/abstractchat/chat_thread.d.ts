import React from "react";
import { type ChatMessage, type ChatMessageCardProps } from "./chat_message_card.js";
export type ChatThreadProps = {
    messages: ChatMessage[];
    className?: string;
    empty?: React.ReactNode;
    autoScroll?: boolean;
    autoScrollThresholdPx?: number;
    /** Optional content after messages, kept inside the same scroll surface. */
    after?: React.ReactNode;
    /** A stable identity for `after`, so newly presented content can follow
     * normal auto-scroll intent without treating arbitrary React nodes as data. */
    afterKey?: string | number | null;
    messageProps?: Omit<ChatMessageCardProps, "message">;
};
export declare function ChatThread(props: ChatThreadProps): React.ReactElement;
export default ChatThread;
//# sourceMappingURL=chat_thread.d.ts.map