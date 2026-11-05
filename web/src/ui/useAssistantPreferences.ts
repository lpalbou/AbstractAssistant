import { useCallback, useEffect, useState } from "react";

export type AssistantPreferences = { design: string; animated: boolean };
const KEY = "abstractassistant.companion";
export const DEFAULT_PREFERENCES: AssistantPreferences = { design: "watch-hover", animated: true };

export function parseAssistantPreferences(raw: string | null): AssistantPreferences {
  try {
    const value = JSON.parse(raw || "null");
    return {
      design: typeof value?.design === "string" && /^[a-z][a-z0-9_-]{0,63}$/.test(value.design) ? value.design : "watch-hover",
      animated: typeof value?.animated === "boolean" ? value.animated : true,
    };
  } catch { return DEFAULT_PREFERENCES; }
}

/** Browser presentation preferences only; entity identity and conversations stay on Gateway. */
export function useAssistantPreferences() {
  const [value, setValue] = useState(() => {
    try { return parseAssistantPreferences(localStorage.getItem(KEY)); } catch { return DEFAULT_PREFERENCES; }
  });
  const [error, setError] = useState("");
  const change = useCallback((next: AssistantPreferences) => {
    setValue(next);
    try { localStorage.setItem(KEY, JSON.stringify(next)); setError(""); }
    catch { setError("This browser could not save the choice. It still applies in this tab."); }
  }, []);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === KEY || event.key === null) {
        try { setValue(parseAssistantPreferences(localStorage.getItem(KEY))); } catch { /* Keep this tab's choice. */ }
      }
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  return { value, change, error };
}
