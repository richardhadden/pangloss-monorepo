import { For } from "solid-js";
import { useModels } from "../context";
import { NavRowButton } from "../primitives";
import { navSections } from "../schema";

/**
 * The sections of the bar (`navSections`): by default the Entities and the Documents of the
 * project, each type a link to its list page, in the order of the type hierarchy; and what the
 * installed apps' `InterfaceConfig`s change. Every button is as wide as the bar, and the text of
 * a type is indented a step more than that of its parent. Links that need a login are shown to someone logged in (`loggedIn`).
 */
export function NavModelList(props: { loggedIn?: boolean }) {
  const models = useModels();
  // (a link an app marks `requires_login` is for someone logged in; the API refuses what needs a login in any case)
  const sections = () =>
    navSections(models)
      .map((section) => ({
        ...section,
        entries: section.entries.filter((entry) => props.loggedIn || !entry.requiresLogin),
      }))
      .filter((section) => section.entries.length > 0);
  return (
    <For each={sections()}>
      {(section) => (
        <section aria-label={section.title}>
          <h2 class="px-3 pt-3 pb-1 text-xs text-slate-500">{section.title}</h2>
          <For each={section.entries}>
            {(entry) => (
              <NavRowButton href={entry.href} indent={entry.depth}>
                {entry.label}
              </NavRowButton>
            )}
          </For>
        </section>
      )}
    </For>
  );
}
