/**
 * The badge row under a reply: one badge per served turn notice (chat_notices.ts). A click hands
 * the notice to the host (`onOpen`, e.g. the record's detail panel); without a host, or when the
 * host returns `false`, the badge opens a small panel under the row with the title and the words,
 * whole. Keyboard: badges are buttons; Escape closes the panel and returns focus to its badge.
 */
import React from "react";
import { type ChatNotice } from "./chat_notices.js";
export type ChatNoticeBadgesProps = {
    notices: readonly ChatNotice[] | null | undefined;
    /**
     * The host's opener for a notice (e.g. the record's detail panel by `record_id`). Return
     * `false` when it opened nothing: the badge then opens its own panel (title and words).
     * Without it every badge opens its own panel.
     */
    onOpen?: (notice: ChatNotice) => void | boolean;
    className?: string;
};
/** One row of badges, one per notice, in the served order (a duplicate once, an empty notice none).
 * Nothing when there is no notice to show. */
export declare function ChatNoticeBadges(props: ChatNoticeBadgesProps): React.ReactElement | null;
//# sourceMappingURL=chat_notice_badges.d.ts.map