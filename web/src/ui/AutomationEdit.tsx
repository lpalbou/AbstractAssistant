import { AfSwitch, isApiError, reviseChanges, reviseFormFrom, type AutomationDefinition, type AutomationSummary } from "@abstractframework/ui-kit";
import { useEffect, useState } from "react";

import { everyChoices, everyLabel, everyOf, titleAfterTask, tokensOf } from "../lib/automations";
import { taskOf } from "./AutomationPage";
import { automationErrorText, type Automations } from "./useAutomations";

type ReviseDefinition = Parameters<typeof reviseChanges>[2];

/**
 * Change an automation as the watch does: its title and its task (each field holds the current
 * text), whether it runs at all and how often, whether each run builds on the earlier ones and how
 * much of them it reads. A title that is the task follows the task while the title itself is not
 * edited. Save sends only what changed, with the revision it was read at (a change made elsewhere
 * meanwhile is refused); leaving with changes asks to save or discard them.
 */
export function AutomationEdit(props: { automations: Automations; summary: AutomationSummary; onDone: () => void }) {
  const { api, refresh } = props.automations;
  const s = props.summary;
  const [definition, setDefinition] = useState<AutomationDefinition | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [title, setTitle] = useState("");
  const [titleEdited, setTitleEdited] = useState(false);
  const [task, setTask] = useState("");
  const [active, setActive] = useState(s.status !== "paused");
  const [every, setEvery] = useState(everyOf(s));
  const [remembers, setRemembers] = useState(s.context_mode === "growing");
  const [tokensText, setTokensText] = useState(s.growing_max_tokens ? String(s.growing_max_tokens) : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getAutomation(s.automation_id).then(
      (d) => {
        if (cancelled) return;
        setDefinition(d.definition);
        setTask(taskOf(d.definition));
        setTitle(d.definition.title || s.title || "");
      },
      () => !cancelled && setLoadFailed(true),
    );
    return () => {
      cancelled = true;
    };
  }, [api, s.automation_id, s.title]);

  const tokens = tokensOf(tokensText);
  const form = (() => {
    const base = reviseFormFrom(s, definition as unknown as ReviseDefinition);
    return { ...base, title: title.trim() || base.title, prompt: definition ? task.trim() || base.prompt : base.prompt, every: every || base.every,
      context: remembers ? ("growing" as const) : ("independent" as const), growingMaxTokens: remembers && tokens ? tokens : base.growingMaxTokens };
  })();
  const revised = definition || !loadFailed ? reviseChanges(s, form, definition as unknown as ReviseDefinition) : null;
  const errors = revised && "errors" in revised ? revised.errors : [];
  const changes = revised && !("errors" in revised) ? revised : null;
  const activeChanged = active !== (s.status !== "paused");
  const tokensProblem = remembers && tokensText.trim() !== "" && tokens === null ? "Numbers only, more than 0." : "";
  const changed = Boolean(changes) || activeChanged;

  const changeTask = (next: string) => {
    setTask(next);
    if (!titleEdited && definition) {
      const followed = titleAfterTask(next.trim(), definition.title, taskOf(definition));
      if (followed !== null) setTitle(followed);
    }
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      if (changes) await api.reviseAutomation(s.automation_id, { changes, expected_revision: definition?.revision ?? s.revision ?? undefined });
      if (activeChanged) await api.sendAutomationCommand(s.automation_id, { type: active ? "automation.resume" : "automation.pause" });
      await refresh();
      props.onDone();
    } catch (e) {
      const inner = isApiError(e) ? e : (e as { error?: unknown }).error;
      setError(isApiError(inner) && inner.status === 409 ? "Changed elsewhere meanwhile. Open it again." : automationErrorText(e));
    } finally {
      setSaving(false);
      setLeaving(false);
    }
  };

  const cancel = () => (changed ? setLeaving(true) : props.onDone());
  const hasEvery = everyOf(s) !== "";

  return (
    <div className="aa-form-page" data-page="automation-edit">
      <form className="aa-form" onSubmit={(e) => { e.preventDefault(); if (changed && !tokensProblem && !errors.length) void save(); }}>
        <h1>Edit</h1>
        {definition ? (
          <>
            <label className="aa-field"><span>Title</span>
              <input value={title} onChange={(e) => { setTitle(e.target.value); setTitleEdited(true); }} />
            </label>
            <label className="aa-field"><span>Task</span>
              <textarea rows={5} value={task} onChange={(e) => changeTask(e.target.value)} />
            </label>
          </>
        ) : loadFailed ? <p className="aa-note aa-note--error" role="alert">Couldn't load this automation.</p> : <p className="aa-note" role="status">Loading…</p>}
        <fieldset className="aa-fieldset"><legend>Runs</legend>
          <AfSwitch variant="row" label="Active" checked={active} onChange={setActive} action="active" />
          {hasEvery && (
            <label className="aa-field"><span>How often</span>
              <select value={every} disabled={!active} onChange={(e) => setEvery(e.target.value)}>
                {everyChoices(everyOf(s)).map((e) => <option key={e} value={e}>{everyLabel(e)}</option>)}
              </select>
            </label>
          )}
        </fieldset>
        <fieldset className="aa-fieldset"><legend>Memory</legend>
          <AfSwitch variant="row" label="Builds on earlier runs" checked={remembers} onChange={setRemembers} action="remembers" />
          {remembers && (
            <label className="aa-field"><span>Reads up to (tokens of its earlier runs)</span>
              <input inputMode="numeric" value={tokensText} placeholder="The gateway's default" onChange={(e) => setTokensText(e.target.value)} aria-invalid={Boolean(tokensProblem)} />
              {tokensProblem ? <small className="aa-field__problem">{tokensProblem}</small> : null}
            </label>
          )}
        </fieldset>
        {errors.map((m) => <p key={m} className="aa-note aa-note--error" role="alert">{m}</p>)}
        {error ? <p className="aa-note aa-note--error" role="alert">{error}</p> : null}
        {leaving ? (
          <div className="aa-form__actions" role="group" aria-label="Save your changes?">
            <span>Save your changes?</span>
            <button type="button" className="aa-button" onClick={props.onDone}>Discard</button>
            <button type="submit" className="aa-button aa-button--primary" disabled={saving || Boolean(tokensProblem) || errors.length > 0}>{saving ? "Saving…" : "Save"}</button>
          </div>
        ) : (
          <div className="aa-form__actions">
            <button type="button" className="aa-button" onClick={cancel}>Cancel</button>
            <button type="submit" className="aa-button aa-button--primary" disabled={!changed || saving || Boolean(tokensProblem) || errors.length > 0}>{saving ? "Saving…" : "Save"}</button>
          </div>
        )}
      </form>
    </div>
  );
}
