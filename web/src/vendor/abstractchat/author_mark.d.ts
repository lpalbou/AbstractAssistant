import React from "react";
import type { ChatAuthorMarkKind, ChatAvatarLook } from "./chat_author.js";
export type ChatAuthorMarkProps = {
    mark: ChatAuthorMarkKind;
    /** The entity's look: a design draws its orb (the kit's `ActivityAvatar`, the renderer the
     * Entity app's identity uses); a colour alone tints the initial disc. */
    look?: ChatAvatarLook | null;
    /** The disc's letter for an entity without a design. */
    initial?: string;
    size: number;
    className?: string;
};
/**
 * The small mark beside an author's name: an entity's orb (its AbstractAvatar design in its
 * colour, still), its initial disc without a design, the agent's mark, or a person. Decorative:
 * the name next to it is the accessible text.
 */
export declare function ChatAuthorMark(props: ChatAuthorMarkProps): React.ReactElement;
//# sourceMappingURL=author_mark.d.ts.map