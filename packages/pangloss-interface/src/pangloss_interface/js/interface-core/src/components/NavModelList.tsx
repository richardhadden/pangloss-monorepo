import { For, Show } from "solid-js";
import { useModels, useTranslations } from "../context";
import { NavRowButton } from "../primitives";
import { navSections } from "../schema";
import type { NavEntry } from "../schema";

/**
 * The sections of the bar (`navSections`): by default the Entities and the Documents of the
 * project, each type a link to its list page, in the order of the type hierarchy; and what the
 * installed apps' `InterfaceConfig`s change. Every button is as wide as the bar, and the text of
 * a type is indented a step more than that of its parent. Links that need a login are shown to someone logged in (`loggedIn`).
 *
 * With a `filter`, only what matches it is listed, without indents: each of its words is to be
 * part of one of the names of the type, in any language (or of the label of a link), regardless
 * of case and accents.
 */
export function NavModelList(props: { loggedIn?: boolean; filter?: string }) {
  const models = useModels();
  const { t, modelName, modelNames } = useTranslations();
  const words = () => foldCase(props.filter ?? "").split(/\s+/).filter((word) => word !== "");
  const matches = (entry: NavEntry) => {
    const wanted = words();
    if (wanted.length === 0) return true;
    const names = (entry.model ? [entry.label, ...modelNames(entry.model)] : [entry.label]).map(foldCase);
    return wanted.every((word) => names.some((name) => name.includes(word)));
  };
  // (the sections the interface makes itself have their title from the words for the kinds; any other is a slot,
  // `nav_section_<title in snake case>`, with the title as written as its English)
  const titleOf = (title: string) => {
    if (title === "Entities") return t("kind_entity_plural", title);
    if (title === "Documents") return t("kind_document_plural", title);
    if (title === "Links") return t("section_links", title);
    const slug = title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    return t(`nav_section_${slug}`, title);
  };
  // (a link an app marks `requires_login` is for someone logged in; the API refuses what needs a login in any case)
  const sections = () =>
    navSections(models)
      .map((section) => ({
        ...section,
        entries: section.entries.filter(
          (entry) => (props.loggedIn || !entry.requiresLogin) && matches(entry),
        ),
      }))
      .filter((section) => section.entries.length > 0);
  const filtering = () => words().length > 0;
  return (
    <>
      <Show when={filtering() && sections().length === 0}>
        <p class="px-3 py-3 text-xs font-normal normal-case text-slate-500">
          {t("nav_filter_none", "No types match")}
        </p>
      </Show>
      <For each={sections()}>
        {(section) => (
          <section aria-label={titleOf(section.title)}>
            <h2 class="px-3 pt-3 pb-1 text-xs text-slate-500">
              {titleOf(section.title)}
            </h2>
            <For each={section.entries}>
              {(entry) => (
                <NavRowButton href={entry.href} indent={filtering() ? 0 : entry.depth}>
                  {entry.model ? modelName(entry.model) : entry.label}
                </NavRowButton>
              )}
            </For>
          </section>
        )}
      </For>
    </>
  );
}

/** Lower case, without accents: what the filter compares */
function foldCase(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
}
