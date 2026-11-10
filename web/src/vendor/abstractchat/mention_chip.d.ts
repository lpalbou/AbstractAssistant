import React from "react";
import type { ChatAvatarLook } from "./chat_author.js";
import { type ChatMentionKind, type ChatMessageMention } from "./mentions.js";
/**
 * A mention chip's face, the same in the composer and in a message: the entity's orb (or the
 * agent's mark) over the "@", then the name. The "@" stays in the words (transparent), so a
 * selection copies "@Name"; the mark is not selectable (in a message its initial is drawn, not
 * written: `drawnInitial`). Only the composer's name carries
 * `data-mention-kind` (`.pc-mention-chip__name[data-mention-kind]` = the chips in the composer,
 * which hosts read); a message's chip carries its kind on the chip itself.
 */
export declare function mentionChipFace(m: {
    kind: ChatMentionKind;
    name: string;
    avatar?: ChatAvatarLook | null;
}, where?: "composer" | "message"): React.ReactNode;
/** How long the pointer (or the keyboard focus) rests on a chip before its card shows. */
export declare const MENTION_CARD_REST_MS = 150;
export type MentionCardPlacement = {
    top: number;
    left: number;
    side: "below" | "above";
};
/**
 * Where a chip's card goes (viewport pixels, `position: fixed`): below the chip, its left edge
 * on the chip's, kept 8 px inside the viewport; above the chip only when it does not fit below
 * and does above; neither: as low as it fits.
 */
export declare function mentionCardPlacement(anchor: {
    top: number;
    left: number;
    bottom: number;
}, size: {
    width: number;
    height: number;
}, viewport: {
    width: number;
    height: number;
}): MentionCardPlacement;
export type ChatMentionChipProps = {
    /** The mention as the message carries it ({id, name, kind, index, start}, `avatar` optional). */
    mention: ChatMessageMention;
    /**
     * The host's card for this mention (e.g. the entity's card from its roster), shown in a small
     * popover below the chip after a 150 ms rest on it (pointer or keyboard focus); it goes on
     * leave, blur or Escape. Called only then; null shows nothing. Absent: the chip is words only.
     */
    renderCard?: (mention: ChatMessageMention) => React.ReactNode | null;
};
/** A mention inside a message's words: the composer's chip, without the ×. */
export declare function ChatMentionChip(props: ChatMentionChipProps): React.ReactElement;
/**
 * The rendered words of a message (`node`, a Markdown tree whose text carried a token for each
 * placed mention: `mentionTokenText`) with each token turned into its chip (`chip`). A token
 * that lands anywhere but in the words (a code block's code, an attribute) gets its "@Name"
 * back. Elements without a token are returned as they were.
 */
export declare function withMentionChips(node: React.ReactNode, placed: readonly ChatMessageMention[], chip: (mention: ChatMessageMention, key: string) => React.ReactNode): React.ReactNode;
//# sourceMappingURL=mention_chip.d.ts.map