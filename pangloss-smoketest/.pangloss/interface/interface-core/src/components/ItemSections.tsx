import { Errored, For, Loading, Show } from "solid-js";
import { useModels, useModules } from "../context";
import { getModel } from "../schema";

/**
 * What the interface modules add after the contents of an item's page (`itemSections`), in the order of the modules,
 * each loaded when first shown, and each deciding itself whether to show anything. The generic item page has them
 * after `ItemContents`; a model's own page (`itemPage`) puts them where it wants.
 */
export function ItemSections(props: { item: Record<string, unknown> }) {
  const definitions = useModels();
  const sections = useModules().itemSections();
  const type = () => (typeof props.item.type === "string" ? props.item.type : "");
  return (
    <Show when={sections.length > 0 && getModel(definitions, type())}>
      {(model) => (
        <For each={sections}>
          {(Section) => (
            <Errored
              fallback={(error) => {
                // (said in the browser's console, so that a module's author sees why there is nothing)
                console.error("A section of an interface module failed:", error());
                return null;
              }}
            >
              <Loading fallback={null}>
                <Section type={type()} id={String(props.item.id ?? "")} item={props.item} model={model()} />
              </Loading>
            </Errored>
          )}
        </For>
      )}
    </Show>
  );
}
