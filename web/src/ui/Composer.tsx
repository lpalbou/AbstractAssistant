import { useRef, useState } from "react";

type Dictation =
  | { available: false; reason: string }
  | { available: true; start: () => Promise<{ cancel: () => void; finish: () => Promise<string> }> };

export function Composer(props: { busy: boolean; onSend: (text: string, files: File[]) => Promise<boolean>; onStop: () => void; dictation: Dictation }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState<null | { cancel: () => void; finish: () => Promise<string> }>(null);
  const [voiceNote, setVoiceNote] = useState("");
  const picker = useRef<HTMLInputElement>(null);

  const submit = async () => {
    const t = text.trim();
    if (!t || sending || props.busy) return;
    setSending(true);
    const ok = await props.onSend(t, files);
    setSending(false);
    if (ok) {
      setText("");
      setFiles([]);
    }
  };

  const toggleMic = async () => {
    if (!props.dictation.available) {
      setVoiceNote(props.dictation.reason);
      return;
    }
    setVoiceNote("");
    if (!recording) {
      try {
        setRecording(await props.dictation.start());
      } catch (err) {
        setVoiceNote(err instanceof Error ? err.message : String(err));
      }
      return;
    }
    const rec = recording;
    setRecording(null);
    setVoiceNote("Transcribing…");
    try {
      const said = await rec.finish();
      // Review before sending (the iPhone's default, backlog 1048).
      setText((prev) => (prev.trim() ? `${prev.trim()}\n${said}` : said));
      setVoiceNote("");
    } catch (err) {
      setVoiceNote(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <form
      className="aa-composer"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      {files.length ? (
        <ul className="aa-composer__files">
          {files.map((f, i) => (
            <li key={`${f.name}:${i}`}>
              {f.name}
              <button type="button" className="aa-link" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {voiceNote ? <p className="aa-composer__note" role="status">{voiceNote}</p> : null}
      <div className="aa-composer__row">
        <button type="button" className="aa-button aa-button--icon" aria-label="Attach files" onClick={() => picker.current?.click()}>
          +
        </button>
        <input
          ref={picker}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            setFiles([...files, ...Array.from(e.target.files || [])]);
            e.target.value = "";
          }}
        />
        <textarea
          className="aa-composer__input"
          rows={1}
          value={text}
          placeholder="Message the Assistant"
          aria-label="Message"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <button
          type="button"
          className={`aa-button aa-button--icon${recording ? " aa-button--recording" : ""}`}
          aria-label={recording ? "Stop dictation" : "Dictate"}
          aria-pressed={Boolean(recording)}
          title={props.dictation.available ? undefined : props.dictation.reason}
          onClick={() => void toggleMic()}
        >
          {recording ? "■" : "Mic"}
        </button>
        {props.busy ? (
          <button type="button" className="aa-button" onClick={props.onStop}>
            Stop
          </button>
        ) : (
          <button type="submit" className="aa-button aa-button--primary" disabled={sending || !text.trim()}>
            {sending ? "Sending…" : "Send"}
          </button>
        )}
      </div>
    </form>
  );
}
