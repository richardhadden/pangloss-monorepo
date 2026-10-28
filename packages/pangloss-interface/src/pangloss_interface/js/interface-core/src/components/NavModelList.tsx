import { For } from "solid-js";
import { useModels } from "../context";
import { NavRowButton } from "../primitives";
import { modelHierarchy } from "../schema";

const SECTIONS = [
  { title: "Entities", kind: "Entity" },
  { title: "Documents", kind: "Document" },
] as const;

/**
 * The Entities and the Documents of the project, each type a link to its list page, in the
 * order of the type hierarchy: every button is as wide as the bar, and the text of a
 * type is indented a step more than that of its parent.
 */
export function NavModelList() {
  const models = useModels();
  return (
    <For each={SECTIONS}>
      {(section) => (
        <section aria-label={section.title}>
          <h2 class="px-3 pt-3 pb-1 text-xs text-slate-400">{section.title}</h2>
          <For each={modelHierarchy(models, section.kind)}>
            {(entry) => (
              <NavRowButton href={`/${entry.model.name}`} indent={entry.depth}>
                {entry.model.name}
              </NavRowButton>
            )}
          </For>
        </section>
      )}
    </For>
  );
}
