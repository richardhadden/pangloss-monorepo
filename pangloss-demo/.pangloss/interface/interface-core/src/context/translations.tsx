import { createContext, createEffect, createSignal, onSettled, untrack, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { ItemTexts, LoadTranslations, TranslationBundle } from "../types";

/** Where the language chosen is kept, so that it is the one next time */
const LANGUAGE_KEY = "pangloss.language";

/** What the words of the page are read through: see `useTranslations` */
export interface Translations {
  /** The language shown (the previous one, until the next has been loaded) */
  language: Accessor<string>;
  languages: Accessor<string[]>;
  /** True while the texts of another language are being fetched: the page fades its words meanwhile */
  loading: Accessor<boolean>;
  /** Show another language: its texts are fetched the first time (with the server function), and the page changes when they are here */
  setLanguage: (code: string) => Promise<void>;
  /**
   * The fixed text `key` of the interface, in the language. `english` is the text to use when
   * there is none (and what a page with no translations shows); `{name}` in a text is
   * replaced by `params.name`.
   */
  t: (key: string, english: string, params?: Record<string, string | number>) => string;
  /** The name of a model, in the singular or the plural (the name itself when it has no text) */
  modelName: (model: string, plural?: boolean) => string;
  fieldName: (model: string, field: string) => string;
  /** A relation that other models make to this one, by its reverse name */
  incomingName: (model: string, reverse: string) => string;
  enumName: (name: string, plural?: boolean) => string;
  memberName: (name: string, member: string) => string;
}

/** Replaces `{name}` in `text` by the parameters (one that is not given stays as it is) */
export function interpolate(text: string, params?: Record<string, string | number>): string {
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    Object.hasOwn(params, name) ? String(params[name]) : whole,
  );
}

/** What there is with no `TranslationsProvider`: the English given, and the names as they are */
const untranslated: Translations = {
  language: () => "en",
  languages: () => ["en"],
  loading: () => false,
  setLanguage: async () => {},
  t: (_key, english, params) => interpolate(english, params),
  modelName: (model) => model,
  fieldName: (_model, field) => field.replaceAll("_", " "),
  incomingName: (_model, reverse) => reverse.replaceAll("_", " "),
  enumName: (name) => name,
  memberName: (_name, member) => member,
};

const TranslationsContext = createContext<Translations>(untranslated);

/**
 * The translations of the page. Pass the bundle of the default language as `initial` (it
 * is always there), and `load`, which fetches the bundle of another language: in the
 * application that is a `"use server"` function, so the texts of a language that nobody
 * chose are not sent to the browser. A language is fetched once, the first time it is
 * chosen; the page shows the previous one until it is here (while `loading()` is true), so
 * that it can fade its words out and back in. The choice is kept in `localStorage`. It is a
 * context, not module state, so that server-side renders do not share it.
 */
export function TranslationsProvider(
  props: ParentProps<{ initial: TranslationBundle; load: LoadTranslations }>,
) {
  const [loaded, setLoaded] = createSignal<Record<string, TranslationBundle>>({});
  const [language, setCurrent] = createSignal<string>(untrack(() => props.initial.language));
  const [loading, setLoading] = createSignal(false);
  let request = 0;

  const bundle = (): TranslationBundle =>
    language() === props.initial.language
      ? props.initial
      : (loaded()[language()] ?? props.initial);

  async function setLanguage(code: string): Promise<void> {
    if (!props.initial.languages.includes(code)) return;
    const ticket = ++request;
    if (code === untrack(language)) {
      // (the language shown is chosen again: a load of another that is under way is given up)
      setLoading(false);
      return;
    }
    if (code !== props.initial.language && !(code in untrack(loaded))) {
      setLoading(true);
      try {
        const fetched = await props.load(code);
        setLoaded((all) => ({ ...all, [code]: fetched }));
      } catch (error) {
        // (the page stays as it is; a choice that could not be made is not kept)
        if (ticket === request) setLoading(false);
        console.error(`The ${code} translations could not be loaded`, error);
        return;
      }
      // (another choice has been made since this was asked for: that one is shown)
      if (ticket !== request) return;
    }
    setCurrent(code);
    setLoading(false);
    try {
      localStorage.setItem(LANGUAGE_KEY, code);
    } catch {
      // (storage unavailable: the choice is just not remembered)
    }
  }

  // The language last chosen (read once settled, so that the server-side render and the first client render agree)
  onSettled(() => {
    try {
      const saved = localStorage.getItem(LANGUAGE_KEY);
      if (saved) void setLanguage(saved);
    } catch {
      // (as above)
    }
  });

  // The page says which language it is in (for the reader, and so that CSS capitalises it correctly), and that
  // it is being changed (styles.css fades the page while it is)
  createEffect(
    () => ({ language: language(), loading: loading() }),
    ({ language, loading }) => {
      document.documentElement.lang = language;
      document.documentElement.toggleAttribute("data-translating", loading);
    },
  );

  const texts = (section: "models" | "enums", name: string): ItemTexts | undefined =>
    bundle()[section][name] ?? props.initial[section][name];
  const plural = (text: ItemTexts | undefined, fallback: string, wanted?: boolean) =>
    wanted ? text?.plural || text?.name || fallback : text?.name || fallback;
  const words = (name: string) => name.replaceAll("_", " ");

  const value: Translations = {
    language,
    languages: () => props.initial.languages,
    loading,
    setLanguage,
    t: (key, english, params) =>
      interpolate(bundle().ui[key] || props.initial.ui[key] || english, params),
    modelName: (model, wanted) => plural(texts("models", model), model, wanted),
    fieldName: (model, field) =>
      texts("models", model)?.fields?.[field]?.name || words(field),
    incomingName: (model, reverse) =>
      texts("models", model)?.incoming?.[reverse]?.name || words(reverse),
    enumName: (name, wanted) => plural(texts("enums", name), name, wanted),
    memberName: (name, member) => texts("enums", name)?.members?.[member]?.name || member,
  };
  return <TranslationsContext value={value}>{props.children}</TranslationsContext>;
}

/**
 * The translations of the page: `const { t, modelName } = useTranslations()`. Without a
 * `TranslationsProvider` above it gives the English that is passed to `t`, so a component
 * works (and is tested) on its own.
 */
export function useTranslations(): Translations {
  return useContext(TranslationsContext);
}
