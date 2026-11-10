# AbstractAssistant in your browser

AbstractAssistant is a voice and conversation interface for AbstractGateway. Open
**Assistant (web)** from Gateway's Apps page or tray Apps menu. Sign in to the same
Gateway to use your existing conversations. The Gateway runs the agent, keeps
history and decides tool permissions; closing this page does not cancel a run.

## Start or continue a conversation

Select a conversation from the sidebar, or use New to start one. On a phone, the
menu button opens Conversations. Search finds loaded conversations by their title.
Type in the message field and send your question. Replies appear in the conversation.
Sending a new message interrupts the previous spoken reply. New and switching
conversations also stop local audio. Opening history does not read it aloud.

The page shows tool approvals and questions inside the conversation when the agent
needs you. Review the tool and its arguments before allowing it. **Allow** lets that
tool run for the rest of this chat when Gateway keeps the chat's permissions; otherwise
it covers this request only, and the card says so. **Allow All** lets every tool run
for the rest of this chat. **Deny** refuses. **Decide later** postpones the choice and
grants no permission. Use Review to return to the pending request. Stop ends the current
request or playback.

## Mention an entity

Type `@` in the message field to see the Assistant and the entities you can mention; type more
of a name to narrow the list, then pick one. It becomes a chip in the message field (its ×
removes it). Text you type after `@` without picking a name stays ordinary text. The first time
you pick an entity in a conversation, a line under the chip reminds you that the entity will
read this conversation's history.

When you send, each entity you mentioned is asked in turn, in the order you picked them, each
once the previous one has answered, so a later entity reads the earlier answers. Each answer appears in the conversation under the
entity's name and look, in the order the answers came, and your message is shown once.
Every reply says who wrote it: the agent's name with an "agent" tag, or the entity's name
and look with an "entity" tag. On a gateway that does not say who wrote a reply, replies
keep their "Assistant" header.

A message that mentions entities goes to them, not to the Assistant: the Assistant does not
answer it, and a line above the message field says "The assistant stays out of this message."
To ask the Assistant too, pick **Assistant** at the top of the `@` list (it has an "agent" tag):
the Assistant then answers only the part of your message meant for it, or says nothing, and the
entities answer as well. When the Assistant does not answer, the conversation shows your words
and the entities' answers, with no empty reply and no waiting. A message without mentions goes
to the Assistant as always.

When an entity keeps something from the exchange (a diary entry, a question, a lesson, an
interest or a realization), its reply shows one badge for each under its words: the kind and
its title. A private diary entry reads "private diary entry" and shows no words; one kept
when a visit closes reads "forming…". Click a badge to read it whole.

A message with mentions sent while the Assistant is still working (in the Avatar view, or an
answer to its question) is answered too: the Assistant reads it as part of the reply it is
writing, and the entities' answers show after the running reply.

When a mention cannot be answered, a sentence above the message field says why:

- "Castor is in another conversation." That entity is busy elsewhere: it is skipped and
  the next one is asked.
- "Castor cannot be mentioned here." That entity is not available to your account: it is
  skipped and the next one is asked.
- An entity that cannot answer right now says so, and nothing more is asked. Your message
  goes back into the message field with only the entities that did not answer still as
  chips. Send the same words again to ask only those: the Assistant is not asked again,
  and an entity that already answered is not asked twice. Different words are a new message.
- "This gateway does not offer mentions yet." Your gateway cannot take mentions: typing `@`
  shows this sentence instead of names.

## Automations

**Automations** in the sidebar (behind the menu button on a phone) lists the tasks that run on
their own: the active ones first, the most recently active at the top, then **Paused** and
**Archived**, each opening on a click. Each card shows how many times it ran, how often it runs
and when it runs next; a number marks results you have not seen, and **Needs you** a run that
waits for you. The archive button asks first; **Restore** under Archived brings one back.

Open an automation to see its latest ten runs as a conversation: what it was asked, then the
answer. Opening it marks its new results seen. **Run** starts a run now; while one runs, **Stop**
ends it (the automation keeps its schedule). **Edit** changes its title, its task, whether it is
active, how often it runs and whether each run builds on its earlier runs (and how much of them
it reads); a change made elsewhere meanwhile is refused, so open it again. Type in the message
field to talk about its latest run: this opens a new conversation about it and never changes
the automation. When a run asks to use a tool, its page shows the request: **Approve** or **Deny**
it, or **Approve all** to allow those tools for this automation's runs. They are listed under
**Allowed for its runs**, and this browser approves them when it sees them, until **Ask again**.
Another kind of request opens with **Answer**, where you can review it.

**New** creates one: what it should do, the flow that runs it (the gateway's default unless you
choose another), its **Tools** (each Off, Ask or Auto; a tool on Ask waits for you), how often it
runs or every day at a time, and whether each run builds on the earlier ones.

## Speak and listen

Tap the orb to begin recording, then tap again to finish. With Hold selected in
Voice settings, hold the orb to record and release it to finish. The browser needs
microphone permission and a secure page: HTTPS, localhost or 127.0.0.1. A plain
HTTP page on another machine cannot use the microphone.

By default, recognized words go into the draft so you can correct them. Enable
**Send what you say automatically** to submit recognized words directly. Microphone
mode, input device and available transcription settings are under Settings → Voice.
The browser records locally; Gateway handles transcription through its configured
speech capability. This is explicit recording, not an always-listening wake word.

Enable **Read new replies aloud** using the speaker control or Voice settings.
It reads new replies from this tab's requests. Use the orb or pause/play control
to pause or resume a selected reply; Stop ends it. A message's speaker control
reads that message on demand. In Voice settings, choose the speaking route and
voice offered by Gateway, or keep its default. Available voices and capabilities
depend on Gateway's installed providers. Browser autoplay rules can require a
click before playback is allowed.

## Appearance and avatars

Settings lets you select an avatar and preview Ready, Listening, Thinking, Working,
Speaking, Waiting and Error silently. Watch particle forms, the iPhone woven orb
and shaded characters remain separate choices. Preview sample loudness does not
record or play audio. Your choice applies immediately. The animation switch and
your system's reduced-motion preference control motion. Hidden pages stop animating.
Avatars with eyes, such as the Hover robot and the Rover, look toward your mouse while
Ready; the orb and every other avatar stay still.
The top-bar appearance button changes the theme.

Listening reacts to measured microphone loudness. Speaking reacts to the reply's
actual playback level after volume and mute. Pauses and silence produce zero
voice level; the avatar never invents a voice signal to appear active.

Ready means the assistant is available. Listening means recording. Thinking and
Working reflect the current request. Speaking follows reply playback. Waiting
means an approval or answer needs you. Error indicates a failed action. The avatar
is a visual representation; it does not run an independent agent.

## Documentation and conversation details

The book button opens the Docs assistant. Ask how to use the browser Assistant;
answers are grounded in this guide. Docs has its own conversation and does not
automatically see or control your main conversation, files or tools. Use New
conversation in its header to start a fresh documentation chat, or Past
conversations to reopen one. Its question field stays at the bottom while messages
scroll above it. Attachment availability depends on Gateway.

Details in the main conversation reveals optional usage, timing and delivery
diagnostics. A structured-output model call may return its text all at once;
this does not mean the reply failed. Errors and pending approvals remain visible.
Copy and export controls use the conversation loaded in the page.

## Settings, privacy and limitations

Gateway owns sign-in, conversations, workflows, model routing and permissions.
This browser keeps appearance, voice and panel preferences locally. Selecting an
avatar does not change an entity's shared identity or voice on other devices.
Use the same Gateway account across clients to access the same conversations.

The desktop, iPhone and Watch apps have their
own interfaces; a native-only feature is not automatically available here.
An unavailable workflow, voice route or connection must be configured on Gateway.
If disconnected, check Gateway connectivity and sign-in before retrying.
