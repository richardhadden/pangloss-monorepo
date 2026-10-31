// The texts of the interface in a language. The gathered file has every language, so it is read
// on the server only: `"use server"` makes this a call to the server from the browser, and the
// file is not in what the browser loads. The default language is asked for at the start (the
// server renders with it); another is asked for the first time it is chosen.
import type { TranslationBundle } from "@pangloss/interface-core";

export async function loadTranslations(language?: string): Promise<TranslationBundle> {
  "use server";
  const { default: all } = await import("@generated/translations");
  const code = language && all.languages.includes(language) ? language : all.default;
  return {
    language: code,
    default: all.default,
    languages: all.languages,
    ui: (all.ui as Record<string, Record<string, string>>)[code] ?? {},
    models: ((all.models as Record<string, unknown>)[code] ?? {}) as TranslationBundle["models"],
    enums: ((all.enums as Record<string, unknown>)[code] ?? {}) as TranslationBundle["enums"],
  };
}
