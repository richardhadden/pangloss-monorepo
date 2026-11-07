import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { useModels, useModules } from "../context";
import { getModel } from "../schema";

/**
 * What the interface modules add after the contents of an item's page (`itemSections`), in the order of the modules,
 * each deciding itself whether to show anything. The generic item page has them after `ItemContents`, in a `Reveal`;
 * a model's own page (`itemPage`) puts them where it wants.
 *
 * Each section is in a `Loading` of its own with no fallback: the boundary the page's `Reveal` orders, so that a
 * section shows after what refers to the item, never before it and then lower down. What a section reads for itself
 * it reads directly, with no boundary of its own (one nested here hydrated wrongly: its server-rendered nodes went
 * unclaimed). Its code is a `lazy` component (which hydrates; a component resolved by hand does not), loaded with the
 * page: `preloadItemPage` starts the imports with the item, and `ready` waits for them under the page's boundary, so
 * that a section's own boundary waits only for what the section reads (on the server each wait that follows another
 * is a pass more, and the development server reports a chain of them).
 */
export function ItemSections(props: { item: Record<string, unknown> }) {
  const definitions = useModels();
  const modules = useModules();
  const sections = modules.itemSections();
  const loaders = modules.itemSectionLoaders();
  const type = () => (typeof props.item.type === "string" ? props.item.type : "");
  // (`true` once the code of every section is there: a value that is written into the page for hydration, as a
  // component is not)
  const ready = createMemo(() => Promise.all(loaders.map((load) => load())).then(() => true));
  return (
    <Show when={sections.length > 0 && ready() && getModel(definitions, type())}>
      {(model) => (
        <For each={sections}>
          {(Section) => (
            <Loading fallback={null}>
              <Errored
                fallback={(error) => {
                  // (said in the browser's console, so that a module's author sees why there is nothing)
                  console.error("A section of an interface module failed:", error());
                  return null;
                }}
              >
                <Section type={type()} id={String(props.item.id ?? "")} item={props.item} model={model()} />
              </Errored>
            </Loading>
          )}
        </For>
      )}
    </Show>
  );
}
