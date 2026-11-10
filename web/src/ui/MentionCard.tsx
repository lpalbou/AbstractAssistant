// The card on a mention chip in a message (panel-chat 0.9.13 `renderMentionCard`, operator
// 2026-11-10): resting on "@Castor" shows the entity's orb, its name and one sentence of its state,
// read from the `GET /entities` rows the `@` list loaded (`entityMentionCards`). The assistant's
// chip, or a name the loaded rows do not hold, has no card (null).
import React from "react";
import { ChatAuthorMark, type ChatMessageMention } from "../vendor/abstractchat/conversation.js";
import type { EntityMentionCard } from "../lib/mentions";
import "./mention_card.css";

export function MentionCard({ card }: { card: EntityMentionCard }): React.ReactElement {
  return (
    <div className="aa-mention-card">
      <ChatAuthorMark mark="entity" look={card.avatar} initial={card.name} size={28} />
      <div className="aa-mention-card__text">
        <span className="aa-mention-card__name">{card.name}</span>
        {card.sentence ? <span className="aa-mention-card__state">{card.sentence}</span> : null}
      </div>
    </div>
  );
}

/** `renderMentionCard`: the card of an entity the loaded rows hold, else null. */
export function mentionCard(mention: ChatMessageMention, cards: ReadonlyMap<string, EntityMentionCard> | null | undefined): React.ReactNode | null {
  if (mention.kind !== "entity") return null;
  const card = cards?.get(mention.id);
  return card ? <MentionCard card={card} /> : null;
}
