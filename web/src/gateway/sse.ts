/**
 * Server-sent events over fetch (not EventSource): EventSource cannot send
 * headers, and a desktop host authenticates with an Authorization header
 * (ADR 0007, Hosts). Same framing rules as the desktop's
 * abstractassistant/gateway/sse_parser.py: `event:`, `data:` (joined with
 * "\n"), `id:`, comment lines (":") ignored, a blank line ends an event.
 */

export type SseEvent = { event: string; data: string; id: string | null };

export class SseParser {
  private buf = "";
  private event = "";
  private data: string[] = [];
  private id: string | null = null;

  /** Feed a decoded text chunk; returns the events it completed. */
  push(chunk: string): SseEvent[] {
    this.buf += chunk;
    const out: SseEvent[] = [];
    let nl: number;
    while ((nl = this.buf.search(/\r\n|\r|\n/)) >= 0) {
      const line = this.buf.slice(0, nl);
      const sepLen = this.buf.startsWith("\r\n", nl) ? 2 : 1;
      this.buf = this.buf.slice(nl + sepLen);
      if (line === "") {
        if (this.data.length || this.event) {
          out.push({ event: this.event || "message", data: this.data.join("\n"), id: this.id });
        }
        this.event = "";
        this.data = [];
        continue;
      }
      if (line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") this.event = value;
      else if (field === "data") this.data.push(value);
      else if (field === "id") this.id = value;
    }
    return out;
  }
}
