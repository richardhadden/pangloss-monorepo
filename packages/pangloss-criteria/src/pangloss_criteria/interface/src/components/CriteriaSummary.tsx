import { useComponent, useModels, useTranslations } from "@pangloss/interface-core";
import { createMemo, For, Match, Switch } from "solid-js";
import type { Accessor } from "solid-js";
import type { Criteria } from "../api";
import { hrefOf } from "../api";
import { cutParts, describeCriteria, describeText, idsOf } from "../describe";
import type { Part } from "../describe";
import { createLabels, missing } from "../labels";
import type { Labels } from "../labels";

/** How long a summary is before it is cut, in characters */
export const SUMMARY_LENGTH = 120;

/**
 * The summary of criteria, as the card and the dialog draw it: the parts (`describeCriteria`), what the entities it
 * names are now (`/api/references`, in the browser), and those of them that are gone
 */
export function createSummary(criteria: Accessor<Criteria | null>) {
  const definitions = useModels();
  const words = useTranslations();
  const parts = createMemo(() => describeCriteria(criteria(), words, definitions));
  const ids = createMemo(() => idsOf(parts()));
  const labels = createLabels(ids);
  return {
    parts,
    labels,
    /** The ids of entities it names that are no longer there */
    missing: () => missing(ids(), labels()),
    /** As plain text */
    text: () => describeText(parts(), labels(), words.t("criteria_deleted_entity", "deleted entity")),
  };
}

/**
 * Criteria said as a sentence: the type, then the conditions, each entity a chip and what is nested in brackets.
 * Past `SUMMARY_LENGTH` characters it is cut with "…", the whole of it on hover (`full`: never cut). An entity that
 * has been deleted is a muted "deleted entity"; one whose label has not come yet, "…"
 */
export function CriteriaSummary(props: { parts: Part[]; labels: Labels | undefined; full?: boolean; class?: string }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const gone = () => t("criteria_deleted_entity", "deleted entity");
  const shown = createMemo(() =>
    props.full ? { parts: props.parts, cut: false } : cutParts(props.parts, props.labels, gone(), SUMMARY_LENGTH),
  );
  return (
    // (inline, so that it wraps as a sentence does: the spaces are in its texts; a line as tall as a chip and its gap)
    <span
      class={["min-w-0 text-sm leading-9 [&_a]:align-middle [&>span]:align-middle", props.class]}
      title={describeText(props.parts, props.labels, gone())}
      data-testid="criteria-summary"
    >
      <For each={shown().parts}>
        {(part) => (
          <Switch>
            <Match when={part.kind === "entity" && part}>
              {(entity) => (
                <Switch fallback={<span class="text-slate-400">…</span>}>
                  <Match when={props.labels?.get(entity().id)}>
                    {(found) => <ReferenceChip type={found().type} label={found().label} href={hrefOf({ type: found().type, id: entity().id })} />}
                  </Match>
                  <Match when={props.labels !== undefined}>
                    <span class="text-slate-400 italic" data-testid="criteria-deleted-entity">
                      {gone()}
                    </span>
                  </Match>
                </Switch>
              )}
            </Match>
            <Match when={part.kind === "type" && part}>
              {(type) => (
                <span class="font-semibold" data-type-info={type().type}>
                  {type().text}
                </span>
              )}
            </Match>
            <Match when={part.kind === "open"}>
              <span class="text-slate-500">(</span>
            </Match>
            <Match when={part.kind === "close"}>
              <span class="text-slate-500">)</span>
            </Match>
            <Match when={part.kind === "text" && part}>{(said) => <span class="whitespace-pre-wrap">{said().text}</span>}</Match>
          </Switch>
        )}
      </For>
    </span>
  );
}
