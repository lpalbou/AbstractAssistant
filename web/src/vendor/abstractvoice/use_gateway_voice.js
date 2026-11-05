// dist/use_gateway_voice.js
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// dist/random_id.js
function insecureContextReason(feature) {
  const g = globalThis;
  if (g.isSecureContext !== false)
    return null;
  return `This page is loaded over http, so ${feature} is unavailable \u2014 open it over https (for example through tailscale serve; the gateway console's Network page explains how) or on the gateway's own computer.`;
}

// dist/voice_devices.js
var md = () => globalThis.navigator?.mediaDevices;
function microphoneErrorSentence(error) {
  const insecure = insecureContextReason("the microphone");
  if (insecure)
    return insecure;
  const name = String(error?.name || "");
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError")
    return "The browser blocked the microphone. Allow it for this site (the icon left of the address), then try again.";
  if (name === "NotFoundError" || name === "DevicesNotFoundError")
    return "No microphone was found. Connect one, then try again.";
  if (name === "OverconstrainedError")
    return "The chosen microphone is not connected. Pick another one in Settings \u2192 Voice.";
  if (name === "NotReadableError" || name === "TrackStartError")
    return "Another app is using the microphone. Close it, then try again.";
  if (!md()?.getUserMedia)
    return "This browser cannot record audio.";
  const detail = String(error?.message || error || "").trim();
  return detail ? `The microphone did not start: ${detail.replace(/\.$/, "")}.` : "The microphone did not start.";
}
async function openMicrophone(deviceId) {
  const m = md();
  if (!m?.getUserMedia)
    throw Object.assign(new Error("This browser cannot record audio."), { name: "NotSupportedError" });
  return m.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId } } : true });
}
function audioContextCtor() {
  const w = globalThis;
  return w.AudioContext || w.webkitAudioContext || null;
}
function inputGainSupported() {
  const C = audioContextCtor();
  return Boolean(C && C.prototype && typeof C.prototype.createMediaStreamDestination === "function");
}
function watchLevel(stream, onLevel, gain = 1) {
  const C = audioContextCtor();
  if (!C)
    return () => void 0;
  const ctx = new C();
  const source = ctx.createMediaStreamSource(stream);
  try {
    void Promise.resolve(ctx.resume()).catch(() => void 0);
  } catch {
  }
  let stop;
  try {
    stop = watchAudioNodeLevel(ctx, source, onLevel, gain);
  } catch (error) {
    source.disconnect();
    void ctx.close?.();
    throw error;
  }
  return () => {
    stop();
    void ctx.close?.();
  };
}
function watchAudioNodeLevel(ctx, source, onLevel, gain = 1) {
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  const data = new Float32Array(analyser.fftSize);
  let alive = true;
  const tick = () => {
    if (!alive)
      return;
    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1)
      sum += data[i] * data[i];
    onLevel(Math.min(1, Math.sqrt(sum / data.length) * 4 * gain));
  };
  const timer = setInterval(tick, 50);
  return () => {
    alive = false;
    clearInterval(timer);
    try {
      source.disconnect(analyser);
    } catch {
    }
    analyser.disconnect?.();
    onLevel(0);
  };
}
function clampVolume(v) {
  const n = Number(v);
  if (v === void 0 || v === null || v === "" || !Number.isFinite(n))
    return 1;
  return Math.min(1, Math.max(0, n));
}

// dist/use_gateway_voice.js
function voiceCaptureMode(value) {
  const v = value && typeof value === "object" ? value.capture_mode : value;
  return v === "toggle" ? "toggle" : "hold";
}
function ttsVoiceKey(voice) {
  if (voice === void 0 || voice === null)
    return "";
  if (typeof voice === "string")
    return `s:${voice}`;
  const keys = Object.keys(voice).filter((k) => voice[k] !== void 0 && voice[k] !== null && voice[k] !== "").sort();
  return `o:${JSON.stringify(keys.map((k) => [k, voice[k]]))}`;
}
async function* streamTtsJsonl(opts) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (opts.signal?.aborted)
    abort();
  else
    opts.signal?.addEventListener("abort", abort, { once: true });
  try {
    const res = await fetch(opts.path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...opts.csrfToken ? { "x-abstract-csrf": opts.csrfToken } : {},
        ...opts.headers || {}
      },
      body: JSON.stringify(opts.body),
      signal: controller.signal
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(ttsErrorDetail(data, res.status));
    }
    if (!res.body)
      throw new Error("TTS stream has no body");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (; ; ) {
      const { done, value } = await reader.read();
      buf += done ? decoder.decode() : decoder.decode(value, { stream: true });
      if (done && buf.trim())
        buf += "\n";
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (!line)
          continue;
        let evt = null;
        try {
          evt = JSON.parse(line);
        } catch {
          throw new Error("TTS stream returned invalid JSON.");
        }
        if (evt && evt.type === "error")
          throw new Error(String(evt.error || "TTS stream error"));
        const b64 = evt && typeof evt.audio_b64 === "string" ? evt.audio_b64 : "";
        if (b64) {
          const bin = atob(b64);
          const bytes = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i += 1)
            bytes[i] = bin.charCodeAt(i);
          yield bytes.buffer;
        }
        if (evt && (evt.type === "done" || evt.type === "cancelled"))
          return;
      }
      if (done)
        throw new Error("TTS stream ended before synthesis completed.");
    }
  } finally {
    opts.signal?.removeEventListener("abort", abort);
    controller.abort();
  }
}
function ttsErrorDetail(data, status) {
  const detail = data && typeof data === "object" ? data.detail : void 0;
  if (detail && typeof detail === "object") {
    const message = detail.message;
    if (typeof message === "string" && message.trim())
      return message.trim();
    return `HTTP ${status}`;
  }
  if (detail !== void 0 && detail !== null && String(detail).trim())
    return String(detail);
  return `HTTP ${status}`;
}
function voiceErrorSentence(prefix, e) {
  const detail = String(e?.message || e || "").trim().replace(/\.$/, "");
  return detail ? `${prefix}: ${detail}.` : `${prefix}.`;
}
var MIN_RECORDING_MS = 350;
function supportsMediaRecorder() {
  if (typeof window === "undefined")
    return false;
  const nav = navigator;
  return Boolean(nav?.mediaDevices?.getUserMedia) && typeof window.MediaRecorder === "function";
}
function supportsTtsWebAudio() {
  if (typeof window === "undefined")
    return false;
  const w = window;
  return Boolean(w?.AudioContext || w?.webkitAudioContext);
}
function chooseVoiceMime() {
  const MR = window.MediaRecorder;
  const isSupported = (t) => {
    try {
      return Boolean(MR?.isTypeSupported?.(t));
    } catch {
      return false;
    }
  };
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus", "audio/ogg"];
  for (const c of candidates)
    if (isSupported(c))
      return c;
  return "";
}
async function decodeAudio(ctx, buf) {
  const copy = buf.slice(0);
  const fn = ctx.decodeAudioData?.bind(ctx);
  if (typeof fn !== "function")
    throw new Error("decodeAudioData not available");
  try {
    const maybe = fn(copy);
    if (maybe && typeof maybe.then === "function")
      return await maybe;
  } catch {
  }
  return await new Promise((resolve, reject) => {
    try {
      fn(copy, resolve, reject);
    } catch (e) {
      reject(e);
    }
  });
}
function wavPrelude(buf) {
  const bytes = new Uint8Array(buf);
  if (bytes.length < 44)
    return null;
  const tag = (off2) => String.fromCharCode(bytes[off2], bytes[off2 + 1], bytes[off2 + 2], bytes[off2 + 3]);
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE")
    return null;
  const view = new DataView(buf);
  let off = 12;
  while (off + 8 <= bytes.length) {
    const id = tag(off);
    const size = view.getUint32(off + 4, true);
    if (id === "data")
      return bytes.slice(0, off + 8);
    off += 8 + size + size % 2;
  }
  return null;
}
function wrapWavSegment(prelude, raw) {
  const rawBytes = new Uint8Array(raw);
  const out = new Uint8Array(prelude.length + rawBytes.length);
  out.set(prelude, 0);
  out.set(rawBytes, prelude.length);
  const view = new DataView(out.buffer);
  view.setUint32(4, out.length - 8, true);
  view.setUint32(prelude.length - 4, rawBytes.length, true);
  return out.buffer;
}
function audioOutputSelectable() {
  const w = globalThis;
  const Ctx = w?.AudioContext;
  return Boolean(Ctx && Ctx.prototype && typeof Ctx.prototype.setSinkId === "function");
}
var applied_sinks = /* @__PURE__ */ new WeakMap();
function apply_sink(ctx, device) {
  const anyCtx = ctx;
  if (typeof anyCtx.setSinkId !== "function" || applied_sinks.get(ctx) === device)
    return;
  applied_sinks.set(ctx, device);
  try {
    void Promise.resolve(anyCtx.setSinkId(device)).catch(() => applied_sinks.delete(ctx));
  } catch {
    applied_sinks.delete(ctx);
  }
}
function useGatewayVoice(opts) {
  const opts_ref = useRef(opts);
  opts_ref.current = opts;
  const set_error = (msg) => opts_ref.current.on_error?.(msg);
  const tts_supported = useMemo(() => supportsTtsWebAudio() && (typeof opts.tts === "function" || typeof opts.tts_stream === "function"), [opts.tts, opts.tts_stream]);
  const voice_ptt_supported = useMemo(() => supportsMediaRecorder() && typeof opts.transcribe === "function", [opts.transcribe]);
  const playback_level = useRef(0);
  const playback_listeners = useRef(/* @__PURE__ */ new Set());
  const playback_meter_stop = useRef(null);
  const publish_playback_level = useCallback((v) => {
    const q = Math.round(Math.min(1, Math.max(0, Number(v) || 0)) * 20) / 20;
    if (q === playback_level.current)
      return;
    playback_level.current = q;
    for (const listener of Array.from(playback_listeners.current))
      listener(q);
  }, []);
  const stop_playback_meter = useCallback(() => {
    const stop = playback_meter_stop.current;
    playback_meter_stop.current = null;
    stop?.();
    publish_playback_level(0);
  }, [publish_playback_level]);
  const [tts_speaking, set_tts_speaking] = useState(false);
  const [tts_playback, set_tts_playback] = useState({ key: "", status: "idle" });
  const tts_playback_ref = useRef(tts_playback);
  const apply_tts_playback = useCallback((next) => {
    tts_playback_ref.current = next;
    if (next.status !== "playing") {
      stop_playback_meter();
      set_tts_speaking(false);
    }
    set_tts_playback((prev) => prev.key === next.key && prev.status === next.status ? prev : next);
  }, [stop_playback_meter]);
  const tts_key_ref = useRef("");
  const tts_loading_key_ref = useRef("");
  const tts_ctx_ref = useRef(null);
  const tts_gain_ref = useRef(null);
  const start_playback_meter = useCallback(() => {
    if (!playback_listeners.current.size || playback_meter_stop.current || tts_playback_ref.current.status !== "playing")
      return;
    const ctx = tts_ctx_ref.current, gain = tts_gain_ref.current;
    if (!ctx || !gain)
      return;
    try {
      playback_meter_stop.current = watchAudioNodeLevel(ctx, gain, (level) => publish_playback_level(ctx.state === "running" && tts_playback_ref.current.status === "playing" ? level : 0));
    } catch {
    }
  }, [publish_playback_level]);
  const subscribe_playback_level = useCallback((fn) => {
    playback_listeners.current.add(fn);
    fn(playback_level.current);
    start_playback_meter();
    return () => {
      playback_listeners.current.delete(fn);
      if (!playback_listeners.current.size)
        stop_playback_meter();
    };
  }, [start_playback_meter, stop_playback_meter]);
  const tts_source_ref = useRef(null);
  const tts_buffer_ref = useRef(null);
  const tts_offset_ref = useRef(0);
  const tts_started_at_ref = useRef(0);
  const tts_stream_gen_ref = useRef(0);
  const tts_stream_abort_ref = useRef(null);
  const tts_segments_ref = useRef([]);
  const tts_seg_idx_ref = useRef(0);
  const tts_sched_ref = useRef([]);
  const tts_stream_done_ref = useRef(true);
  const tts_paused_ref = useRef(false);
  const tts_audio_id_ref = useRef("");
  const tts_resume_attempt_ref = useRef(0);
  const tts_resume_error_ref = useRef(false);
  const tts_audio_id = (key, text) => {
    const voice = ttsVoiceKey(opts_ref.current.tts_voice);
    return voice ? `${key}${text}${voice}` : "";
  };
  const sync_tts_playback = () => {
    const key = tts_key_ref.current;
    if (!key)
      return;
    const hasAudio = Boolean(tts_source_ref.current || tts_sched_ref.current.length);
    const status = tts_paused_ref.current ? "paused" : hasAudio ? tts_ctx_ref.current?.state === "running" ? "playing" : "paused" : tts_stream_done_ref.current ? "idle" : tts_segments_ref.current.length ? "playing" : "loading";
    apply_tts_playback({ key: status === "idle" ? "" : key, status });
    const audible = status === "playing" && hasAudio && tts_ctx_ref.current?.state === "running" && Boolean(tts_gain_ref.current?.gain.value);
    set_tts_speaking(audible);
    if (audible)
      start_playback_meter();
    else
      stop_playback_meter();
  };
  const request_tts_resume = (ctx) => {
    if (ctx.state === "running")
      return;
    const attempt = tts_resume_attempt_ref.current;
    const failed = () => {
      if (attempt === tts_resume_attempt_ref.current && tts_ctx_ref.current === ctx && tts_key_ref.current) {
        sync_tts_playback();
        tts_resume_error_ref.current = true;
        set_error?.("Audio playback is paused by the browser. Press Play to try again.");
      }
    };
    try {
      void ctx.resume().then(() => {
        if (attempt !== tts_resume_attempt_ref.current)
          return;
        sync_tts_playback();
        if (ctx.state === "running" && tts_resume_error_ref.current) {
          tts_resume_error_ref.current = false;
          set_error?.("");
        }
      }, failed);
    } catch {
      failed();
    }
  };
  const ensure_tts_webaudio = () => {
    try {
      const w = globalThis;
      const Ctx = w?.AudioContext || w?.webkitAudioContext;
      if (!Ctx)
        return null;
      if (!tts_ctx_ref.current) {
        const ctx2 = new Ctx();
        const gain2 = ctx2.createGain();
        gain2.gain.value = 1;
        gain2.connect(ctx2.destination);
        tts_ctx_ref.current = ctx2;
        tts_gain_ref.current = gain2;
        ctx2.onstatechange = sync_tts_playback;
      }
      const ctx = tts_ctx_ref.current;
      const gain = tts_gain_ref.current;
      if (!ctx || !gain)
        return null;
      apply_sink(ctx, opts_ref.current.output_device_id || "");
      gain.gain.value = clampVolume(opts_ref.current.volume) * (opts_ref.current.muted ? 0 : 1);
      return { ctx, gain };
    } catch {
      return null;
    }
  };
  useEffect(() => {
    const gain = tts_gain_ref.current;
    if (gain) {
      gain.gain.value = clampVolume(opts.volume) * (opts.muted ? 0 : 1);
      sync_tts_playback();
    }
  }, [opts.volume, opts.muted]);
  const stop_tts_source = useCallback(() => {
    stop_playback_meter();
    const scheduled = tts_sched_ref.current;
    tts_sched_ref.current = [];
    for (const s of scheduled) {
      try {
        s.src.onended = null;
      } catch {
      }
      try {
        s.src.stop();
      } catch {
      }
      try {
        s.src.disconnect();
      } catch {
      }
    }
    const src = tts_source_ref.current;
    tts_source_ref.current = null;
    if (!src)
      return;
    try {
      src.onended = null;
    } catch {
    }
    try {
      src.stop();
    } catch {
    }
    try {
      src.disconnect();
    } catch {
    }
  }, [stop_playback_meter]);
  const stop_tts = useCallback(() => {
    tts_resume_attempt_ref.current += 1;
    stop_tts_source();
    tts_stream_gen_ref.current += 1;
    tts_stream_abort_ref.current?.abort();
    tts_stream_abort_ref.current = null;
    tts_segments_ref.current = [];
    tts_seg_idx_ref.current = 0;
    tts_stream_done_ref.current = true;
    tts_paused_ref.current = false;
    tts_loading_key_ref.current = "";
    tts_key_ref.current = "";
    tts_buffer_ref.current = null;
    tts_audio_id_ref.current = "";
    tts_offset_ref.current = 0;
    tts_started_at_ref.current = 0;
    apply_tts_playback({ key: "", status: "idle" });
  }, [stop_tts_source, apply_tts_playback]);
  const voice_key = ttsVoiceKey(opts.tts_voice);
  const voice_key_ref = useRef(voice_key);
  useEffect(() => {
    if (voice_key_ref.current === voice_key)
      return;
    voice_key_ref.current = voice_key;
    if (tts_playback_ref.current.status === "paused")
      stop_tts();
  }, [voice_key, stop_tts]);
  useEffect(() => {
    return () => {
      stop_tts();
      try {
        tts_gain_ref.current?.disconnect();
      } catch {
      }
      try {
        void tts_ctx_ref.current?.close();
      } catch {
      }
      tts_ctx_ref.current = null;
      tts_gain_ref.current = null;
      tts_buffer_ref.current = null;
    };
  }, []);
  const start_tts_playback = async (key, buffer, offset) => {
    const generation = tts_stream_gen_ref.current;
    const engine = ensure_tts_webaudio();
    if (!engine)
      throw new Error("TTS playback is not supported in this browser");
    const { ctx, gain } = engine;
    if (generation !== tts_stream_gen_ref.current)
      return;
    stop_tts_source();
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(gain);
    const dur = Number.isFinite(Number(buffer.duration)) ? Number(buffer.duration) : 0;
    const off = Math.max(0, Math.min(Number(offset || 0), dur > 0 ? Math.max(0, dur - 0.01) : 0));
    tts_started_at_ref.current = ctx.currentTime - off;
    tts_offset_ref.current = off;
    tts_source_ref.current = source;
    tts_key_ref.current = key;
    source.onended = () => {
      if (tts_source_ref.current !== source)
        return;
      tts_source_ref.current = null;
      tts_offset_ref.current = 0;
      tts_started_at_ref.current = 0;
      tts_key_ref.current = "";
      apply_tts_playback({ key: "", status: "idle" });
    };
    source.start(0, off);
    sync_tts_playback();
  };
  const start_stream_segment = (key, gen) => {
    if (gen !== tts_stream_gen_ref.current || tts_paused_ref.current)
      return;
    const engine = ensure_tts_webaudio();
    if (!engine)
      return;
    const segs = tts_segments_ref.current;
    const sched = tts_sched_ref.current;
    const last = sched.length ? sched[sched.length - 1] : null;
    let idx = last ? last.idx + 1 : tts_seg_idx_ref.current;
    if (!last && idx >= segs.length) {
      if (tts_stream_done_ref.current) {
        tts_key_ref.current = "";
        tts_offset_ref.current = 0;
        tts_started_at_ref.current = 0;
        apply_tts_playback({ key: "", status: "idle" });
      } else {
        sync_tts_playback();
      }
      return;
    }
    const { ctx, gain } = engine;
    const now = Number(ctx.currentTime || 0);
    let when = last ? Math.max(last.at + last.dur, now) : now + 0.02;
    for (; idx < segs.length; idx++) {
      const buffer = segs[idx];
      const dur = Number.isFinite(Number(buffer.duration)) ? Number(buffer.duration) : 0;
      const off = !last && idx === tts_seg_idx_ref.current ? Math.max(0, Math.min(Number(tts_offset_ref.current || 0), dur > 0 ? Math.max(0, dur - 0.01) : 0)) : 0;
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gain);
      const entry = { src: source, idx, at: when, off, dur: Math.max(0, dur - off) };
      source.onended = () => {
        if (gen !== tts_stream_gen_ref.current)
          return;
        const list = tts_sched_ref.current;
        const at = list.indexOf(entry);
        if (at < 0)
          return;
        list.splice(at, 1);
        tts_seg_idx_ref.current = entry.idx + 1;
        tts_offset_ref.current = 0;
        if (!list.length)
          start_stream_segment(key, gen);
      };
      source.start(when, off);
      tts_sched_ref.current.push(entry);
      when += entry.dur;
    }
    tts_started_at_ref.current = tts_sched_ref.current.length ? tts_sched_ref.current[0].at - tts_sched_ref.current[0].off : 0;
    tts_key_ref.current = key;
    sync_tts_playback();
  };
  const stream_position = (now) => {
    const sched = tts_sched_ref.current;
    if (!sched.length)
      return { idx: tts_seg_idx_ref.current, off: 0 };
    for (const s of sched) {
      if (now < s.at)
        return { idx: s.idx, off: s.off };
      if (now < s.at + s.dur)
        return { idx: s.idx, off: s.off + (now - s.at) };
    }
    const tail = sched[sched.length - 1];
    return { idx: tail.idx + 1, off: 0 };
  };
  const start_tts_stream = async (key, text, streamFn) => {
    const engine = ensure_tts_webaudio();
    if (!engine) {
      set_error?.("This browser cannot play spoken replies.");
      return;
    }
    stop_tts_source();
    const gen = ++tts_stream_gen_ref.current;
    tts_stream_abort_ref.current?.abort();
    const streamAbort = new AbortController();
    tts_stream_abort_ref.current = streamAbort;
    tts_segments_ref.current = [];
    tts_seg_idx_ref.current = 0;
    tts_stream_done_ref.current = false;
    tts_paused_ref.current = false;
    tts_buffer_ref.current = null;
    tts_offset_ref.current = 0;
    tts_started_at_ref.current = 0;
    tts_key_ref.current = key;
    tts_loading_key_ref.current = key;
    tts_audio_id_ref.current = tts_audio_id(key, text);
    apply_tts_playback({ key, status: "loading" });
    set_error?.("");
    let prelude = null;
    try {
      for await (const bytes of streamFn(text, streamAbort.signal)) {
        if (gen !== tts_stream_gen_ref.current)
          return;
        let buffer;
        try {
          buffer = await decodeAudio(engine.ctx, bytes);
          if (!prelude)
            prelude = wavPrelude(bytes);
        } catch {
          if (!prelude)
            continue;
          try {
            buffer = await decodeAudio(engine.ctx, wrapWavSegment(prelude, bytes));
          } catch {
            continue;
          }
        }
        if (gen !== tts_stream_gen_ref.current)
          return;
        tts_segments_ref.current.push(buffer);
        if (!tts_paused_ref.current) {
          tts_loading_key_ref.current = "";
          start_stream_segment(key, gen);
        }
      }
      if (gen !== tts_stream_gen_ref.current)
        return;
      tts_stream_done_ref.current = true;
      if (tts_segments_ref.current.length === 0) {
        set_error?.("Reading aloud failed: the voice engine returned no audio.");
        stop_tts();
        return;
      }
      if (!tts_sched_ref.current.length && !tts_paused_ref.current)
        start_stream_segment(key, gen);
    } catch (e) {
      if (gen !== tts_stream_gen_ref.current)
        return;
      set_error?.(voiceErrorSentence("Reading aloud failed", e));
      stop_tts();
    } finally {
      if (tts_stream_abort_ref.current === streamAbort)
        tts_stream_abort_ref.current = null;
    }
  };
  const toggle_tts = useCallback(async (msg_key, text) => {
    tts_resume_attempt_ref.current += 1;
    const key = String(msg_key || "").trim();
    const t = String(text || "").trim();
    if (!key || !t)
      return;
    const tts = opts_ref.current.tts;
    const tts_stream = opts_ref.current.tts_stream;
    if (typeof tts !== "function" && typeof tts_stream !== "function") {
      set_error?.("Reading aloud is not available on this gateway.");
      return;
    }
    const engine = ensure_tts_webaudio();
    if (!engine) {
      set_error?.("This browser cannot play spoken replies.");
      return;
    }
    const playback = tts_playback_ref.current;
    if (playback.status !== "playing")
      request_tts_resume(engine.ctx);
    const is_same = playback.key === key;
    if (is_same && playback.status === "paused" && !tts_paused_ref.current && tts_audio_id_ref.current !== "" && tts_audio_id_ref.current === tts_audio_id(key, t) && (tts_source_ref.current || tts_sched_ref.current.length)) {
      sync_tts_playback();
      return;
    }
    if (is_same && playback.status === "playing") {
      if (tts_sched_ref.current.length) {
        const pos = stream_position(Number(engine.ctx.currentTime || 0));
        tts_seg_idx_ref.current = pos.idx;
        tts_offset_ref.current = pos.off;
      } else if (tts_source_ref.current) {
        const off = Math.max(0, engine.ctx.currentTime - Number(tts_started_at_ref.current || 0));
        tts_offset_ref.current = off;
      } else {
        tts_offset_ref.current = 0;
      }
      tts_paused_ref.current = true;
      stop_tts_source();
      apply_tts_playback({ key, status: "paused" });
      return;
    }
    const reusable = is_same && playback.status === "paused" && tts_audio_id_ref.current !== "" && tts_audio_id_ref.current === tts_audio_id(key, t);
    if (is_same && playback.status === "paused" && !reusable)
      stop_tts();
    if (reusable) {
      if (tts_segments_ref.current.length > 0) {
        set_error?.("");
        tts_paused_ref.current = false;
        start_stream_segment(key, tts_stream_gen_ref.current);
        return;
      }
      const buffer = tts_buffer_ref.current;
      if (buffer) {
        set_error?.("");
        tts_paused_ref.current = false;
        try {
          await start_tts_playback(key, buffer, tts_offset_ref.current);
        } catch (e) {
          set_error?.(voiceErrorSentence("Reading aloud failed", e));
          apply_tts_playback({ key: "", status: "idle" });
        }
        return;
      }
    }
    if (is_same && playback.status === "loading")
      return;
    if (typeof tts_stream === "function") {
      await start_tts_stream(key, t, tts_stream);
      return;
    }
    stop_tts_source();
    tts_stream_gen_ref.current += 1;
    tts_stream_abort_ref.current?.abort();
    tts_stream_abort_ref.current = null;
    const gen = tts_stream_gen_ref.current;
    tts_segments_ref.current = [];
    tts_seg_idx_ref.current = 0;
    tts_stream_done_ref.current = true;
    tts_paused_ref.current = false;
    tts_buffer_ref.current = null;
    tts_offset_ref.current = 0;
    tts_started_at_ref.current = 0;
    tts_key_ref.current = key;
    tts_loading_key_ref.current = key;
    tts_audio_id_ref.current = tts_audio_id(key, t);
    apply_tts_playback({ key, status: "loading" });
    set_error?.("");
    try {
      const bytes = await tts(t);
      if (tts_loading_key_ref.current !== key || tts_stream_gen_ref.current !== gen)
        return;
      const buffer = await decodeAudio(engine.ctx, bytes);
      if (tts_loading_key_ref.current !== key || tts_stream_gen_ref.current !== gen)
        return;
      tts_buffer_ref.current = buffer;
      tts_offset_ref.current = 0;
      await start_tts_playback(key, buffer, 0);
    } catch (e) {
      if (tts_stream_gen_ref.current !== gen)
        return;
      if (tts_loading_key_ref.current === key) {
        tts_loading_key_ref.current = "";
        tts_key_ref.current = "";
        apply_tts_playback({ key: "", status: "idle" });
      }
      set_error?.(voiceErrorSentence("Reading aloud failed", e));
    }
  }, []);
  const [voice_ptt_recording, set_voice_ptt_recording] = useState(false);
  const [voice_ptt_busy, set_voice_ptt_busy] = useState(false);
  const voice_ptt_recording_ref = useRef(false);
  const voice_ptt_supported_ref = useRef(voice_ptt_supported);
  voice_ptt_supported_ref.current = voice_ptt_supported;
  const apply_recording = useCallback((v) => {
    voice_ptt_recording_ref.current = v;
    set_voice_ptt_recording((prev) => prev === v ? prev : v);
  }, []);
  const voice_ptt_busy_ref = useRef(false);
  const voice_ptt_stream_ref = useRef(null);
  const voice_ptt_recorder_ref = useRef(null);
  const voice_ptt_chunks_ref = useRef([]);
  const voice_ptt_mime_ref = useRef("");
  const voice_ptt_generation = useRef(0);
  const voice_ptt_start_pending = useRef(false);
  const voice_ptt_stop_pending = useRef(false);
  const [voice_ptt_since, set_voice_ptt_since] = useState(0);
  const voice_ptt_started_ms = useRef(0);
  const voice_ptt_gain_ctx = useRef(null);
  const voice_ptt_level_ref = useRef(0);
  const level_listeners = useRef(/* @__PURE__ */ new Set());
  const voice_ptt_level_stop = useRef(null);
  const apply_level = useCallback((v) => {
    const q = Math.round(Math.min(1, Math.max(0, Number(v) || 0)) * 20) / 20;
    if (q === voice_ptt_level_ref.current)
      return;
    voice_ptt_level_ref.current = q;
    for (const listener of Array.from(level_listeners.current))
      listener(q);
  }, []);
  const subscribe_level = useCallback((fn) => {
    level_listeners.current.add(fn);
    fn(voice_ptt_level_ref.current);
    return () => {
      level_listeners.current.delete(fn);
    };
  }, []);
  const transcript_listeners = useRef(/* @__PURE__ */ new Set());
  const add_transcript_listener = useCallback((fn) => {
    transcript_listeners.current.add(fn);
    return () => {
      transcript_listeners.current.delete(fn);
    };
  }, []);
  function stop_voice_ptt_tracks() {
    const stop_level = voice_ptt_level_stop.current;
    voice_ptt_level_stop.current = null;
    try {
      stop_level?.();
    } catch {
    }
    apply_level(0);
    try {
      voice_ptt_stream_ref.current?.getTracks?.().forEach((t) => {
        try {
          t.stop();
        } catch {
        }
      });
    } catch {
    }
    voice_ptt_stream_ref.current = null;
    const gainCtx = voice_ptt_gain_ctx.current;
    voice_ptt_gain_ctx.current = null;
    try {
      void gainCtx?.close();
    } catch {
    }
  }
  const cancel_voice_ptt_recording = useCallback(() => {
    voice_ptt_generation.current += 1;
    voice_ptt_start_pending.current = false;
    const recorder = voice_ptt_recorder_ref.current;
    if (recorder) {
      recorder.onstop = null;
      recorder.ondataavailable = null;
      recorder.onerror = null;
      try {
        recorder.stop();
      } catch {
      }
    }
    voice_ptt_recorder_ref.current = null;
    stop_voice_ptt_tracks();
    apply_recording(false);
    voice_ptt_busy_ref.current = false;
    set_voice_ptt_busy(false);
    set_voice_ptt_since(0);
    voice_ptt_chunks_ref.current = [];
  }, [apply_recording]);
  useEffect(() => () => cancel_voice_ptt_recording(), [cancel_voice_ptt_recording]);
  async function transcribe_voice_blob(blob, mime) {
    set_error?.("");
    if (voice_ptt_busy_ref.current)
      return;
    const held_ms = voice_ptt_started_ms.current ? Date.now() - voice_ptt_started_ms.current : Infinity;
    if (!blob || !blob.size || held_ms < MIN_RECORDING_MS) {
      set_voice_ptt_since(0);
      set_error?.("The recording was too short. Hold the microphone button while you speak, or tap it once to start and again to stop.");
      return;
    }
    const transcribe = opts_ref.current.transcribe;
    if (typeof transcribe !== "function") {
      set_error?.("Speech to text is not available on this gateway.");
      return;
    }
    voice_ptt_busy_ref.current = true;
    const generation = voice_ptt_generation.current;
    set_voice_ptt_busy(true);
    set_voice_ptt_since(Date.now());
    try {
      const result = await transcribe(blob, mime);
      const info = typeof result === "string" || !result ? { text: String(result || "") } : result;
      const text = String(info.text || "").trim();
      if (generation !== voice_ptt_generation.current)
        return;
      if (text) {
        opts_ref.current.on_transcript?.(text, { ...info, text });
        for (const listener of Array.from(transcript_listeners.current))
          listener(text, { ...info, text });
      } else
        set_error?.("Nothing was heard. Check the microphone in Settings \u2192 Voice (Test), then try again.");
    } catch (e) {
      if (generation === voice_ptt_generation.current) {
        const detail = String(e?.message || e || "").trim().replace(/\.$/, "");
        set_error?.(detail ? `Transcription failed: ${detail}.` : "Transcription failed.");
      }
    } finally {
      if (generation === voice_ptt_generation.current) {
        voice_ptt_busy_ref.current = false;
        set_voice_ptt_busy(false);
        set_voice_ptt_since(0);
      }
    }
  }
  const start_voice_ptt_recording = useCallback(async () => {
    set_error?.("");
    if (!voice_ptt_supported_ref.current) {
      set_error?.(insecureContextReason("the microphone") ?? "Voice recording is not supported in this browser (MediaRecorder/getUserMedia unavailable).");
      return;
    }
    if (voice_ptt_busy_ref.current)
      return;
    if (voice_ptt_start_pending.current)
      return;
    if (voice_ptt_recording_ref.current || voice_ptt_recorder_ref.current)
      return;
    voice_ptt_chunks_ref.current = [];
    const generation = voice_ptt_generation.current;
    voice_ptt_start_pending.current = true;
    voice_ptt_stop_pending.current = false;
    try {
      const stream = await openMicrophone(opts_ref.current.input_device_id || "");
      if (generation !== voice_ptt_generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      if (voice_ptt_stop_pending.current) {
        voice_ptt_stop_pending.current = false;
        stream.getTracks().forEach((track) => track.stop());
        set_voice_ptt_since(0);
        return;
      }
      voice_ptt_stream_ref.current = stream;
      const level_gain = Number(opts_ref.current.input_gain ?? 1);
      try {
        voice_ptt_level_stop.current = watchLevel(stream, apply_level, Number.isFinite(level_gain) && level_gain > 0 ? level_gain : 1);
      } catch {
      }
      const mime = chooseVoiceMime();
      voice_ptt_mime_ref.current = mime;
      let recorded = stream;
      const input_gain = Number(opts_ref.current.input_gain ?? 1);
      if (Number.isFinite(input_gain) && input_gain > 0 && input_gain !== 1 && inputGainSupported()) {
        const C = globalThis.AudioContext || globalThis.webkitAudioContext;
        const ctx = new C();
        const g = ctx.createGain();
        g.gain.value = input_gain;
        const dest = ctx.createMediaStreamDestination();
        ctx.createMediaStreamSource(stream).connect(g);
        g.connect(dest);
        voice_ptt_gain_ctx.current = ctx;
        recorded = dest.stream;
      }
      const rec = mime ? new MediaRecorder(recorded, { mimeType: mime }) : new MediaRecorder(recorded);
      voice_ptt_recorder_ref.current = rec;
      rec.ondataavailable = (ev) => {
        if (generation !== voice_ptt_generation.current)
          return;
        try {
          if (ev?.data)
            voice_ptt_chunks_ref.current.push(ev.data);
        } catch {
        }
      };
      rec.onerror = () => {
        if (generation !== voice_ptt_generation.current)
          return;
        set_error?.("Recording failed. Try again, or pick another microphone in Settings \u2192 Voice.");
      };
      rec.onstop = () => {
        if (generation !== voice_ptt_generation.current)
          return;
        apply_recording(false);
        stop_voice_ptt_tracks();
        voice_ptt_recorder_ref.current = null;
        try {
          const b = new Blob(voice_ptt_chunks_ref.current, { type: voice_ptt_mime_ref.current || "" });
          void transcribe_voice_blob(b, voice_ptt_mime_ref.current);
        } catch (e) {
          set_error?.(voiceErrorSentence("The recording could not be prepared", e));
        }
      };
      rec.start();
      voice_ptt_started_ms.current = Date.now();
      set_voice_ptt_since(voice_ptt_started_ms.current);
      apply_recording(true);
    } catch (e) {
      if (generation !== voice_ptt_generation.current)
        return;
      stop_voice_ptt_tracks();
      voice_ptt_recorder_ref.current = null;
      apply_recording(false);
      set_voice_ptt_since(0);
      set_error?.(microphoneErrorSentence(e));
    } finally {
      if (generation === voice_ptt_generation.current)
        voice_ptt_start_pending.current = false;
    }
  }, []);
  const stop_voice_ptt_recording = useCallback(() => {
    const rec = voice_ptt_recorder_ref.current;
    if (voice_ptt_start_pending.current && !rec) {
      voice_ptt_stop_pending.current = true;
      return;
    }
    if (!voice_ptt_recording_ref.current || !rec)
      return;
    apply_recording(false);
    try {
      rec.stop();
    } catch (e) {
      set_error?.(voiceErrorSentence("The recording could not stop", e));
    }
  }, []);
  useEffect(() => {
    if (!voice_ptt_recording || opts_ref.current.stop_on_pointerup === false)
      return;
    if (opts_ref.current.stop_on_pointerup === void 0 && voiceCaptureMode(opts_ref.current.capture_mode) === "toggle")
      return;
    const on_up = () => stop_voice_ptt_recording();
    window.addEventListener("pointerup", on_up);
    window.addEventListener("pointercancel", on_up);
    return () => {
      window.removeEventListener("pointerup", on_up);
      window.removeEventListener("pointercancel", on_up);
    };
  }, [voice_ptt_recording]);
  return {
    tts_supported,
    tts_playback,
    tts_speaking,
    toggle_tts,
    stop_tts,
    voice_ptt_supported,
    voice_ptt_recording,
    voice_ptt_busy,
    start_voice_ptt_recording,
    stop_voice_ptt_recording,
    cancel_voice_ptt_recording,
    voice_ptt_since,
    subscribe_level,
    subscribe_playback_level,
    voice_capture_mode: voiceCaptureMode(opts.capture_mode),
    add_transcript_listener
  };
}
var use_gateway_voice_default = useGatewayVoice;
export {
  MIN_RECORDING_MS,
  audioOutputSelectable,
  use_gateway_voice_default as default,
  streamTtsJsonl,
  ttsErrorDetail,
  ttsVoiceKey,
  useGatewayVoice,
  voiceCaptureMode,
  voiceErrorSentence
};
