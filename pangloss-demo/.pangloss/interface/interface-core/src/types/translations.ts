/** The texts of one model or enum, in one language (what `pangloss interface translations gather` writes) */
export interface ItemTexts {
  name: string;
  plural: string;
  description?: string;
  help?: string;
  fields?: Record<string, { name: string; plural: string; help: string }>;
  incoming?: Record<string, { name: string; plural: string; help: string }>;
  members?: Record<string, { name: string }>;
}

/**
 * Everything in one language: what a server function sends when the language is asked for.
 * Where a text is missing in the language the gathered file already has the default
 * language's, so a bundle is complete.
 */
export interface TranslationBundle {
  language: string;
  /** The default language, and all the languages there are (the same in every bundle) */
  default: string;
  languages: string[];
  ui: Record<string, string>;
  models: Record<string, ItemTexts>;
  enums: Record<string, ItemTexts>;
}

export type LoadTranslations = (language?: string) => Promise<TranslationBundle>;
