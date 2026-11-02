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
needs you. Review the tool and its arguments before allowing it. **Allow once**
applies to that request. **Allow for this chat**, when available, uses Gateway's
session policy. **Decide later** postpones the choice and grants no permission.
Use Review to return to the pending request. Stop ends the current request or playback.

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
