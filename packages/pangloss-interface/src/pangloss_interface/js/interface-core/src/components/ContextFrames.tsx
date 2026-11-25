import { Show } from "solid-js";
import type { ParentProps } from "solid-js";
import type { PathEntry } from "../api";
import { useModels, useTranslations } from "../context";
import { kindRule, kindTint, spaceTint } from "../primitives";
import { getModel } from "../schema";
import { Head } from "./Head";
import { SpaceBands } from "./SpaceBands";
import { nestedClass } from "./form/styles";

/**
 * What an item is inside (`contextPath`, outermost first), round the item, each as it is in the item
 * that holds it and in the form: a semantic space is a band of its colour, and a document is its full
 * head, a link to it, then the name of its field that holds what follows (as the field is named on the
 * document's own page), with what is in it indented under a rule in the colour of its type. Which it is
 * is the entry's `kind`; the model gives the colour.
 */
export function ContextFrames(
  props: ParentProps<{ path: readonly PathEntry[]; depth?: number }>,
) {
  const definitions = useModels();
  const { fieldName } = useTranslations();
  const entry = () => props.path[0];
  const model = () => getModel(definitions, entry()?.type ?? "");
  const rule = () => kindRule(model()?.kind, model()?.interfaceMeta?.colour);
  // (the bands alone count for how deep a colour is: a document between two spaces has none)
  const depth = () => props.depth ?? 0;
  const inner = (innerDepth: number) => (
    <ContextFrames path={props.path.slice(1)} depth={innerDepth}>
      {props.children}
    </ContextFrames>
  );
  return (
    <Show when={props.path.length > 0} fallback={props.children}>
      <Show
        when={entry()?.kind === "space"}
        fallback={
          <div class="flex w-full min-w-0 flex-col">
            <Head
              type={entry()!.type}
              tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
              rule={rule()}
              href={`/${entry()!.type}/${encodeURIComponent(entry()!.id)}`}
            />
            <div class={["ml-2 pt-6", nestedClass, rule()]}>
              {/* (one child: the gap of the rule's column is not to come between the parts of the item) */}
              <div class="min-w-0">
                {/* (the field that holds what follows, named as a row of the document's page names it) */}
                <div class="mb-2 text-xs font-semibold text-slate-500 uppercase" data-context-field={entry()!.field}>
                  {fieldName(entry()!.type, entry()!.field)}
                </div>
                {inner(depth())}
              </div>
            </div>
          </div>
        }
      >
        {/* (its tint again at half strength, under the band: a little more colour than a space inside an item has,
            since this is all that marks the space round the whole page. Not at full strength: bands nest, and it adds up) */}
        <div class="relative isolate w-full min-w-0">
          <div
            aria-hidden="true"
            class={[
              "pointer-events-none absolute inset-0 -z-10 rounded-xs opacity-50",
              spaceTint(model()?.interfaceMeta?.colour, depth()),
            ]}
          />
          <SpaceBands spaces={[entry()!.type]} depth={depth()} stacked>
            {inner(depth() + 1)}
          </SpaceBands>
        </div>
      </Show>
    </Show>
  );
}
