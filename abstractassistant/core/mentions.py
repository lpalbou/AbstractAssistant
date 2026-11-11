"""`@entity` mentions in the desktop chat (operator 2026-11-11: "following the same logic as other apps").

A Qt-free port of the web Assistant's `web/src/lib/mentions.ts` (and of how `web/src/ui/Workspace.tsx`
sends a message with mentions), over AbstractGateway's mention contract
(`untracked/entity-mentions-2026-11-08/CONTRACT-mentions.md` and its Additions). Divergence between
the two is a bug.

The rules
---------
- The names come from `GET /api/gateway/entities` (the entities this account may see), read ONCE per
  chat open (`EntityRoster.from_payload`), never per keystroke. The composer offers `@agent` first
  (`AGENT_MENTION`), then the entities (`MentionCandidate`). A row the gateway marks as broken
  (`error`) is not offered.
- A mention is a STRUCTURED chip picked from that list (`Mention`: id, name, kind, index, start).
  The text is never read for `@` (no-heuristics ruling): nothing here parses a message.
- Who the message reaches (operator 2026-11-10): the chips ride `POST runs/start` as `mentions`
  (`start_run_mentions`: entity slugs and the reserved "agent", in pick order). A message that
  mentions entities and not `@agent` does not reach the session agent: the gateway records the
  person's words as a turn and starts no agent run (`agent: "not_addressed"` + `turn_id`). A message
  without chips reaches the agent as always.
- The entities are asked one after the other, in their order (`index` = the gateway's
  `mention_index`), each after the previous one returned, so the second sees the first one's answer;
  an entity named twice is asked once (`deliver_mentions`). Each mention names the person's turn that
  carries the same words (`repeat_of`: the agent's run, or the turn kept when the agent was not
  addressed) and has its own `mention_id` (`<message>:<entity>:<index>`), so a resend gets the first
  answer back instead of asking again.
- Refusals: 409 = "<Name> is in another conversation.", go on with the next; 404 `entity_not_found` =
  "<Name> cannot be mentioned here.", go on; 503 = the gateway's own sentence, stop (the words go back
  to the composer with the chips not answered: `MentionResend`); 422 `repeat_of_unknown` = one
  sentence, stop; a gateway without the route (a plain 404/405, no code) = `MENTIONS_UNAVAILABLE`,
  stop. Anything else (a refused connection, a malformed answer) = "<Name> did not answer: <why>",
  stop. Never a silent drop.
- The person's words show once: a mention turn repeats them (`repeat_of`); a reloaded chat folds the
  repeat into the turn it repeats (gateway/history_seed.py) and labels each answer with its `author`.

The worker API (abstractassistant/ui/gateway_worker.py, for the palette)
-----------------------------------------------------------------------
Build the turn's worker as today (`controller.build_chat_worker(prompt=text, ...)`), then, BEFORE
`start()`, hand it the composer's chips:

    worker.set_mentions(mentions, resend=held_resend_or_None)

- `mentions`: the chips of the send, `Sequence[Mention]` in text order (`index` 0, 1, ...; `start`
  = where its "@Name" sits in the text). `@agent` is `Mention(id="agent", kind="agent", ...)`.
  No chips (or never calling `set_mentions`) = today's send, unchanged.
- `resend`: the `MentionResend` the previous send's `MentionsSummary.resend` handed back (an entity
  could not answer). When the person sends the SAME words again with chips (and no `@agent`), only
  those mentions are asked, with the same turn and ids: no upload, no new turn, no transcript row
  for the person's words (the palette must not append them either). Otherwise it is ignored.

Signals, for one message, in this order (all queued to the GUI thread):

- `mention_asked(Mention)`: that entity is being asked now (its answer bubble shows its dots).
- `mention_answered(Mention, MentionAnswer)`: its answer (`answer.reply`, `answer.author`,
  `answer.run_id` = the session turn). The worker has ALREADY appended it to the transcript as an
  assistant row whose metadata carries `author` (`mention_answer_metadata`): the palette refreshes
  its history and draws the bubble from that row (`bubble_author(metadata)`), it never appends it.
- `mention_skipped(Mention, str)`: that entity was not asked or refused (another conversation,
  cannot be mentioned); the sentence shows at once and its pending bubble goes, BEFORE the next
  entity is asked.
- `mentions_done(MentionsSummary)`: once per message that carried entity chips, before `finished`.
  `status_line` = the one line to show ("" = nothing); `stopped` = an entity could not answer: put
  `text` back in the composer with the chips `unsent`, and keep `resend` for the next send;
  `unavailable` = this gateway has no mention door (disable the chips); `agent_addressed` = False
  when the gateway started no agent run (no agent reply is coming: no "no written reply" line);
  `aborted` = the person pressed Stop (the remaining entities were not asked).

`event_emitted` also carries `{"type": "agent_not_addressed", "turn_id": ...}` right after a start
the gateway did not route to the agent.

DOM/Qt-free; checked by tests/basic/test_mentions.py.
"""

from __future__ import annotations

import secrets
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: The one sentence an older gateway gets (no mention route).
MENTIONS_UNAVAILABLE = "This gateway does not offer mentions yet."

#: The reserved slug that names the conversation's own agent in `mentions` (the gateway's rule:
#: no entity can be called "agent").
AGENT_MENTION = "agent"

#: The chip kinds a composer sends.
MENTION_KINDS = ("entity", "agent")

#: The author kinds a turn carries (AbstractRuntime core.turn_author).
AUTHOR_KINDS = ("entity", "agent", "person")

#: The metadata `kind` of an entity's answer the worker appends to the transcript.
MENTION_ANSWER_KIND = "mention_answer"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _record(value: Any) -> Optional[Mapping[str, Any]]:
    return value if isinstance(value, Mapping) else None


# ---------------------------------------------------------------------------------------------
# Looks, candidates, chips
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AvatarLook:
    """An entity's orb: `identity.avatar.{style, color}` of its `GET /entities` row."""

    style: Optional[str] = None
    color: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {"style": self.style, "color": self.color}


def _look_of(value: Any) -> Optional[AvatarLook]:
    look = _record(value)
    style = _text(look.get("style")) if look else ""
    color = _text(look.get("color")) if look else ""
    return AvatarLook(style=style or None, color=color or None) if (style or color) else None


@dataclass(frozen=True)
class MentionCandidate:
    """One name the composer's `@` list offers: an entity (its slug, the id the mention door
    resolves) or the conversation's agent (`AGENT_MENTION`)."""

    id: str
    name: str
    kind: str
    avatar: Optional[AvatarLook] = None


@dataclass(frozen=True)
class Mention:
    """A chip as sent: the candidate it was picked from, `index` = its place among the message's
    mentions in text order (0, 1, ...: the gateway's `mention_index`), `start` = where its "@Name"
    sits in the sent text (`text[start:start + len(name) + 1] == "@" + name`)."""

    id: str
    name: str
    kind: str
    index: int
    start: Optional[int] = None

    def __post_init__(self) -> None:
        if self.kind not in MENTION_KINDS:
            raise ValueError(f"A mention's kind is one of {list(MENTION_KINDS)}, not {self.kind!r}.")
        if not _text(self.id):
            raise ValueError("A mention needs the id it was picked with.")
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise ValueError(f"A mention's index is a number from 0, not {self.index!r}.")

    @property
    def key(self) -> str:
        """The chip's identity (`kind:id`): an entity named twice is one chip."""
        return f"{self.kind}:{self.id}"

    @classmethod
    def from_candidate(cls, candidate: MentionCandidate, *, index: int, start: Optional[int] = None) -> "Mention":
        return cls(id=candidate.id, name=candidate.name, kind=candidate.kind, index=int(index), start=start)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"id": self.id, "name": self.name, "kind": self.kind, "index": self.index}
        if isinstance(self.start, int):
            out["start"] = self.start
        return out


def entity_candidates(payload: Any) -> List[MentionCandidate]:
    """The entities a `GET /entities` answer offers: one per listed row, its `slug` as the id, its
    display `name`, its look from the row's identity record (`identity.avatar`). A row the gateway
    marks as broken (`error`) is not offered; a row without a slug is malformed and said so."""
    rows = _record(payload).get("entities") if _record(payload) else None
    if not isinstance(rows, list):
        return []
    out: List[MentionCandidate] = []
    for raw in rows:
        row = _record(raw)
        if row is None:
            warnings.warn(f"#MALFORMED: an entity row of GET /entities is not an object: {raw!r}")
            continue
        if "error" in row:
            continue
        slug = _text(row.get("slug"))
        if not slug:
            warnings.warn(f"#MALFORMED: an entity row of GET /entities has no slug: {dict(row)!r}")
            continue
        identity = _record(row.get("identity"))
        out.append(
            MentionCandidate(
                id=slug,
                name=_text(row.get("name")) or slug,
                kind="entity",
                avatar=_look_of(identity.get("avatar") if identity else None),
            )
        )
    return out


def agent_candidate(name: str = "Assistant") -> MentionCandidate:
    """The chip that addresses the conversation's agent (`@agent`)."""
    return MentionCandidate(id=AGENT_MENTION, name=_text(name) or "Assistant", kind="agent")


def mention_roster(entities: Sequence[MentionCandidate], agent_name: Optional[str] = None) -> List[MentionCandidate]:
    """The names the composer offers: the agent first, then the entities."""
    return [agent_candidate(agent_name or "Assistant"), *entities]


def match_candidates(candidates: Sequence[MentionCandidate], query: str) -> List[MentionCandidate]:
    """The names that start with what was typed after `@` (name or id, any case)."""
    q = str(query or "").strip().lower()
    if not q:
        return list(candidates)
    return [c for c in candidates if c.name.lower().startswith(q) or c.id.lower().startswith(q)]


@dataclass(frozen=True)
class EntityCard:
    """What the card on a mention chip shows: the entity's name, its orb, one sentence of its state."""

    id: str
    name: str
    avatar: Optional[AvatarLook]
    sentence: str


def entity_state_sentence(name: str, state: Any) -> str:
    """The state sentence of a roster row (`state`, the record `GET /state` serves): "Castor is in a
    conversation." while visited (`mode: "visiting"`), else "Castor is <state>."; "" without one."""
    row = _record(state)
    if row and _text(row.get("mode")) == "visiting":
        return f"{name} is in a conversation."
    word = _text(row.get("state")) if row else ""
    return f"{name} is {word}." if word else ""


def entity_mention_cards(payload: Any) -> Dict[str, EntityCard]:
    """The cards of the rows the `@` list offers (`entity_candidates`), by slug."""
    rows = _record(payload).get("entities") if _record(payload) else None
    offered = {c.id: c for c in entity_candidates(payload)}
    out: Dict[str, EntityCard] = {}
    for raw in rows if isinstance(rows, list) else []:
        row = _record(raw)
        candidate = offered.get(_text(row.get("slug"))) if row else None
        if row is None or candidate is None or candidate.id in out:
            continue
        out[candidate.id] = EntityCard(
            id=candidate.id,
            name=candidate.name,
            avatar=candidate.avatar,
            sentence=entity_state_sentence(candidate.name, row.get("state")),
        )
    return out


@dataclass(frozen=True)
class EntityRoster:
    """One read of `GET /entities` for a chat: the `@` list (agent first) and the chips' cards.
    Read once when the chat opens and kept; read again only after a refusal named an entity
    (`refresh_after`)."""

    candidates: Tuple[MentionCandidate, ...] = ()
    cards: Mapping[str, EntityCard] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any, *, agent_name: Optional[str] = None) -> "EntityRoster":
        return cls(
            candidates=tuple(mention_roster(entity_candidates(payload), agent_name)),
            cards=entity_mention_cards(payload),
        )

    def match(self, query: str) -> List[MentionCandidate]:
        return match_candidates(self.candidates, query)

    def look_of(self, mention: Mention) -> Optional[AvatarLook]:
        card = self.cards.get(mention.id) if mention.kind == "entity" else None
        return card.avatar if card else None

    @staticmethod
    def refresh_after(summary: "MentionsSummary") -> bool:
        """A name the gateway refused (hidden, elsewhere) is read again on the next `@`."""
        return bool(summary.notes)


# ---------------------------------------------------------------------------------------------
# A message's chips
# ---------------------------------------------------------------------------------------------


def unique_mentions(mentions: Sequence[Mention]) -> List[Mention]:
    """Each chip once: the first occurrence keeps its place and index."""
    seen: set = set()
    out: List[Mention] = []
    for m in mentions:
        if m.key in seen:
            continue
        seen.add(m.key)
        out.append(m)
    return out


def mentioned_entities(mentions: Sequence[Mention]) -> List[Mention]:
    """The entity chips of a message (the ones the mention door is asked about)."""
    return [m for m in mentions if m.kind == "entity"]


def pending_mentions(mentions: Sequence[Mention]) -> List[Mention]:
    """The entities whose answers a message waits for, in the order they are asked (one bubble each)."""
    return unique_mentions(sorted(mentioned_entities(mentions), key=lambda m: m.index))


def start_run_mentions(mentions: Sequence[Mention]) -> List[str]:
    """`mentions` of `POST runs/start`: the chips in pick order (`index`), each once, an entity by
    its slug, the agent chip as "agent". [] for a message without chips (the body then carries no
    `mentions` key and the agent answers as always)."""
    out: List[str] = []
    for m in sorted(mentions, key=lambda m: m.index):
        slug = AGENT_MENTION if m.kind == "agent" else m.id
        if slug not in out:
            out.append(slug)
    return out


def sent_message_mentions(
    mentions: Sequence[Mention], look_of: Callable[[Mention], Optional[AvatarLook]]
) -> List[Dict[str, Any]]:
    """The chips a sent message shows in its bubble (the user row's `metadata["mentions"]`): every chip
    the send carried ({id, name, kind, index, start}) with its look from the `@` list."""
    out: List[Dict[str, Any]] = []
    for m in mentions:
        row = m.to_dict()
        look = look_of(m)
        if look is not None:
            row["avatar"] = look.to_dict()
        out.append(row)
    return out


def mint_message_id() -> str:
    """A fresh message id: "msg-" and 24 random hex digits."""
    return f"msg-{secrets.token_hex(12)}"


def mention_message_key(repeat_of: Optional[str], mint: Callable[[], str] = mint_message_id) -> str:
    """The message part of its mentions' ids: the person's turn (`repeat_of`) when there is one,
    else an id minted now. Taken once per message; a resend passes the first send's."""
    return _text(repeat_of) or mint()


def mention_id(message: str, mention: Mention) -> str:
    """One mention's `mention_id`: `<message>:<entity>:<mention_index>`."""
    key = _text(message)
    if not key:
        raise ValueError("A mention needs its message key (mention_id).")
    return f"{key}:{mention.id}:{mention.index}"


@dataclass(frozen=True)
class MentionResend:
    """What a send stopped partway leaves for the resend: the conversation, the words, the person's
    turn they were sent with (`repeat_of`, "" when none), the message key its `mention_id`s were
    built from, and the mentions not answered (the failed one and those after it)."""

    session_id: str
    text: str
    repeat_of: str
    message_key: str
    unsent: Tuple[Mention, ...]


def mention_resend(pending: Optional[MentionResend], text: str, mentions: Sequence[Mention]) -> Optional[List[Mention]]:
    """The mentions to ask when a send RESENDS `pending`, or None when it is a new message (the kit's
    `mentionResend`): the same words (trimmed) with at least one chip asks ONLY those chips, each
    once, with the same turn; an unsent chip keeps its first index, a chip added since is numbered
    after them. A message with `@agent` is a new message (it starts the agent's turn)."""
    if pending is None or not mentions or str(text or "").strip() != str(pending.text or "").strip():
        return None
    if any(m.kind == "agent" for m in mentions):
        return None
    first = {m.key: m.index for m in pending.unsent}
    nxt = max((m.index + 1 for m in pending.unsent), default=0)
    seen: set = set()
    out: List[Mention] = []
    for m in mentions:
        if m.key in seen:
            continue
        seen.add(m.key)
        index = first.get(m.key)
        if index is None:
            index, nxt = nxt, nxt + 1
        out.append(Mention(id=m.id, name=m.name, kind=m.kind, index=index, start=m.start))
    return sorted(out, key=lambda m: m.index)


# ---------------------------------------------------------------------------------------------
# Authors
# ---------------------------------------------------------------------------------------------


def read_author(value: Any) -> Optional[Dict[str, Any]]:
    """A turn's `author` in its full shape ({kind, name, entity_id, identity_ref, avatar}), or None
    when absent (an older gateway) or not an author (a malformed one is said so)."""
    if value is None:
        return None
    row = _record(value)
    kind = _text(row.get("kind")) if row else ""
    if row is None or kind not in AUTHOR_KINDS:
        warnings.warn(f"#MALFORMED: a turn's author is not an author: {value!r}")
        return None
    look = _record(row.get("avatar"))
    return {
        "kind": kind,
        "name": _text(row.get("name")) or None,
        "entity_id": _text(row.get("entity_id")) or None,
        "identity_ref": _text(row.get("identity_ref")) or None,
        "avatar": {"style": _text(look.get("style")) or None, "color": _text(look.get("color")) or None} if look else None,
    }


def bubble_author(metadata: Any) -> Optional[Dict[str, Any]]:
    """Who a transcript row's bubble names: an entity's (or a person's) answer names its author; an
    agent's answer, or a row without an author (an older gateway), is drawn exactly as today
    ("Assistant") and gets None."""
    meta = _record(metadata)
    author = _record(meta.get("author")) if meta else None
    if author is None or _text(author.get("kind")) not in ("entity", "person"):
        return None
    return dict(author)


# ---------------------------------------------------------------------------------------------
# The mention door
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MentionRequest:
    """One `POST sessions/{session_id}/mentions` body."""

    entity: str
    text: str
    mention_index: int
    mention_id: str
    repeat_of: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "entity": self.entity,
            "text": self.text,
            "mention_index": self.mention_index,
            "mention_id": self.mention_id,
        }
        if self.repeat_of:
            body["repeat_of"] = self.repeat_of
        return body


@dataclass(frozen=True)
class MentionAnswer:
    """What the mention door answered (200): the session turn the answer is (`run_id`), the entity's
    reply, who wrote it, and what its turn formed (`notices`)."""

    run_id: str
    reply: str
    mention_index: int
    author: Optional[Dict[str, Any]] = None
    turn_id: Optional[str] = None
    repeat_of: Optional[str] = None
    notices: Tuple[Dict[str, Any], ...] = ()
    mirrors: Tuple[Dict[str, Any], ...] = ()


def mention_answer_from(payload: Any, request: MentionRequest, *, name: str = "") -> MentionAnswer:
    """The door's 200 body as an answer. A body without the session turn's id is not an answer: it
    raises with a sentence (never a silent drop)."""
    who = name or request.entity
    body = _record(payload)
    run_id = _text(body.get("run_id")) if body else ""
    if not run_id:
        raise RuntimeError(f"The gateway answered the mention of {who} without its turn.")
    index = body.get("mention_index")
    return MentionAnswer(
        run_id=run_id,
        reply=body.get("reply") if isinstance(body.get("reply"), str) else "",
        mention_index=index if isinstance(index, int) and not isinstance(index, bool) else request.mention_index,
        author=read_author(body.get("author")),
        turn_id=_text(body.get("turn_id")) or None,
        repeat_of=_text(body.get("repeat_of")) or None,
        notices=tuple(dict(n) for n in body.get("notices") or [] if isinstance(n, Mapping)),
        mirrors=tuple(dict(m) for m in body.get("mirrors") or [] if isinstance(m, Mapping)),
    )


def mention_answer_metadata(answer: MentionAnswer, mention: Mention, *, repeat_of: str = "") -> Dict[str, Any]:
    """The transcript row metadata of an entity's answer: its turn (`run_id`), who wrote it
    (`author`; the chip's name when the gateway sent none), the turn it repeats, its notices."""
    author = answer.author or {
        "kind": "entity",
        "name": mention.name,
        "entity_id": None,
        "identity_ref": None,
        "avatar": None,
    }
    meta: Dict[str, Any] = {
        "kind": MENTION_ANSWER_KIND,
        "run_id": answer.run_id,
        "author": dict(author),
        "mention": mention.to_dict(),
    }
    if repeat_of or answer.repeat_of:
        meta["repeat_of"] = repeat_of or answer.repeat_of
    if answer.notices:
        meta["notices"] = [dict(n) for n in answer.notices]
    return meta


#: How a refused mention is handled (see the module doc).
REFUSALS = ("route_missing", "elsewhere", "not_offered", "cannot_answer", "repeat_unknown", "failed")


def mention_refusal(error: BaseException) -> str:
    """The refusal an error from the mention door stands for, from its `status` and `code` (the
    client's GatewayCodedError). Every refusal of the door is coded; an uncoded 404/405 is a gateway
    without the route. An error without a status (a refused connection) is "failed"."""
    status = getattr(error, "status", 0)
    status = status if isinstance(status, int) else 0
    code = _text(getattr(error, "code", ""))
    if status in (404, 405) and not code:
        return "route_missing"
    if status == 409:
        return "elsewhere"
    if status == 404:
        return "not_offered"
    if status == 503:
        return "cannot_answer"
    if status == 422 and code == "repeat_of_unknown":
        return "repeat_unknown"
    return "failed"


def _detail_of(error: BaseException) -> str:
    return _text(getattr(error, "detail", "")) or str(error) or error.__class__.__name__


def elsewhere_sentence(name: str) -> str:
    return f"{name} is in another conversation."


def not_offered_sentence(name: str) -> str:
    return f"{name} cannot be mentioned here."


def repeat_unknown_sentence(name: str) -> str:
    return f"{name} was not asked: the gateway did not find your message in this conversation."


def failed_sentence(name: str, detail: str) -> str:
    return f"{name} did not answer: {detail}"


@dataclass
class MentionDelivery:
    """What `deliver_mentions` did, in order."""

    #: The message key every `mention_id` was built from (a resend passes it back).
    message: str
    #: (mention, answer) for each answer, in the order they came.
    answered: List[Tuple[Mention, MentionAnswer]] = field(default_factory=list)
    #: One sentence per mention that was skipped (another conversation, not offered).
    notes: List[str] = field(default_factory=list)
    #: The gateway has no mention route: nothing more was sent.
    unavailable: bool = False
    #: Why the remaining mentions were not sent (an entity could not answer, the call failed).
    stopped: Optional[str] = None
    #: Not answered because of `stopped` (or a Stop): that mention and every one after it.
    unsent: List[Mention] = field(default_factory=list)
    #: The person pressed Stop: the remaining mentions were not asked.
    aborted: bool = False


def deliver_mentions(
    *,
    text: str,
    mentions: Sequence[Mention],
    post: Callable[[MentionRequest], MentionAnswer],
    repeat_of: str = "",
    message: str = "",
    should_stop: Optional[Callable[[], bool]] = None,
    on_asked: Optional[Callable[[Mention], None]] = None,
    on_answer: Optional[Callable[[Mention, MentionAnswer], None]] = None,
    on_skipped: Optional[Callable[[Mention, str], None]] = None,
) -> MentionDelivery:
    """Ask the message's entities one after the other, in their order, each after the previous one
    returned; `on_answer` runs for each answer, `on_skipped` for each refusal that does not stop the
    run, both before the next entity is asked. Only entities go to the door: the agent chip rode the
    start (`start_run_mentions`). `should_stop` (a Stop) is read before each ask."""
    stopping = should_stop or (lambda: False)
    key = _text(message) or mention_message_key(repeat_of)
    out = MentionDelivery(message=key)
    asked = pending_mentions(mentions)
    for at, mention in enumerate(asked):
        if stopping():
            out.aborted = True
            out.unsent = asked[at:]
            return out
        request = MentionRequest(
            entity=mention.id,
            text=text,
            mention_index=mention.index,
            mention_id=mention_id(key, mention),
            repeat_of=_text(repeat_of) or None,
        )
        if on_asked is not None:
            on_asked(mention)
        try:
            answer = post(request)
        except Exception as error:  # noqa: BLE001 - every refusal is mapped to a sentence below
            if stopping():
                out.aborted = True
                out.unsent = asked[at:]
                return out
            refusal = mention_refusal(error)
            if refusal == "route_missing":
                out.unavailable = True
                return out
            if refusal in ("elsewhere", "not_offered"):
                sentence = (elsewhere_sentence if refusal == "elsewhere" else not_offered_sentence)(mention.name)
                out.notes.append(sentence)
                if on_skipped is not None:
                    on_skipped(mention, sentence)
                continue
            out.unsent = asked[at:]
            if refusal == "repeat_unknown":
                out.stopped = repeat_unknown_sentence(mention.name)
            elif refusal == "cannot_answer":
                out.stopped = _detail_of(error)
            else:
                out.stopped = failed_sentence(mention.name, _detail_of(error))
            return out
        out.answered.append((mention, answer))
        if on_answer is not None:
            on_answer(mention, answer)
    return out


def mention_status_line(outcome: MentionDelivery) -> str:
    """The one line about the mentions just sent: their refusals and stops ("" = nothing to say).
    Never an informational line (operator 2026-11-10 23:02)."""
    parts = [*outcome.notes, MENTIONS_UNAVAILABLE if outcome.unavailable else "", outcome.stopped or ""]
    return " ".join(p for p in parts if p)


@dataclass(frozen=True)
class MentionsSummary:
    """`mentions_done`'s payload: how one message's mentions went (see the module doc)."""

    text: str
    turn_id: str
    agent_addressed: bool
    message_key: str
    answered: Tuple[Tuple[Mention, MentionAnswer], ...] = ()
    notes: Tuple[str, ...] = ()
    unavailable: bool = False
    stopped: Optional[str] = None
    unsent: Tuple[Mention, ...] = ()
    aborted: bool = False
    resend: Optional[MentionResend] = None
    status_line: str = ""

    @classmethod
    def of(
        cls, outcome: MentionDelivery, *, session_id: str, text: str, turn_id: str, agent_addressed: bool
    ) -> "MentionsSummary":
        resend = None
        if outcome.stopped and outcome.unsent:
            resend = MentionResend(
                session_id=session_id,
                text=text,
                repeat_of=turn_id,
                message_key=outcome.message,
                unsent=tuple(outcome.unsent),
            )
        return cls(
            text=text,
            turn_id=turn_id,
            agent_addressed=agent_addressed,
            message_key=outcome.message,
            answered=tuple(outcome.answered),
            notes=tuple(outcome.notes),
            unavailable=outcome.unavailable,
            stopped=outcome.stopped,
            unsent=tuple(outcome.unsent),
            aborted=outcome.aborted,
            resend=resend,
            status_line=mention_status_line(outcome),
        )


def view_agent_not_addressed(view: Any) -> bool:
    """A replay view of a person's turn no agent was asked to answer: the gateway serves
    `agent_addressed: false` on the view's body (AbstractGateway replay_view `served_json`)."""
    body = _record(view)
    return bool(body) and body.get("agent_addressed") is False
