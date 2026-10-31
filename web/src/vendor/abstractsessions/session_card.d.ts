import React from "react";
export interface SessionCardProps {
    sessionId: string;
    title: string;
    selected?: boolean;
    unread?: boolean;
    needsAttention?: boolean;
    working?: boolean;
    turnCount?: number | null;
    toolCount?: number | null;
    countsPartial?: boolean;
    updatedAt?: string | number | null;
    nowMs: number;
    onOpen: () => void;
    onArchive?: () => void;
    archiveDisabled?: boolean;
    disabled?: boolean;
    className?: string;
}
/** Compact, controlled conversation card. Reading, transport and archive confirmation belong to the host. */
export declare function SessionCard(p: SessionCardProps): React.ReactElement;
//# sourceMappingURL=session_card.d.ts.map