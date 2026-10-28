import { getThemeSpec } from "@abstractframework/ui-kit";

/** The design tokens' palette (web/design/tokens.css) follows the kit theme's group: the app
 * sets `data-theme="dark"|"light"` on the root from the theme the person picked. */
export function themeGroup(themeId: string): "dark" | "light" {
  return getThemeSpec(themeId)?.group === "light" ? "light" : "dark";
}
