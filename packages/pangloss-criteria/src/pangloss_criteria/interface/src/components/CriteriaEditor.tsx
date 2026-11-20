import {
  headBarClass,
  kindRule,
  kindTint,
  nestedClass,
  plainTint,
  typeChipClass,
  useItemForm,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import type { EditCardProps } from "@pangloss/interface-core";
import { createMemo, createSignal, onSettled, Show, untrack } from "solid-js";
import type { Preview } from "../api";
import { criteriaOf, describableTypes, namedIds, sameCriteria, savedResult, withCriteria, wordingOf } from "../value";
import { PreviewResult } from "./Candidates";
import { CriteriaDialog } from "./CriteriaDialog";
import type { CriteriaDone } from "./CriteriaDialog";
import { createSummary, CriteriaSummary } from "./CriteriaSummary";
import { BAR_BUTTON, PencilIcon } from "./parts";

/**
 * A description (`MatchesCriteria`) in a form, in place of the box a reified relation has: a head bar with its type,
 * the summary of its criteria, a pencil that opens them in a dialog (`CriteriaDialog`) and ✕; under it the wording,
 * and what the criteria find. What the dialog last found is shown as not saved yet; a saved description that has not
 * been changed shows what the server found. A new one (just added) opens the dialog at once, and Cancel there takes it
 * out again, as it never had criteria.
 *
 * It writes only what a description is written with (its `wording` and `criteria`) and keeps what the read gave; when
 * the criteria change, what the server worked out of the old ones goes (`withCriteria`).
 */
export default function CriteriaEditor(props: EditCardProps) {
  const form = useItemForm();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const criteria = createMemo(() => criteriaOf(props.value));
  const wording = () => wordingOf(props.value);
  const id = () => (typeof props.value.id === "string" ? props.value.id : undefined);
  // (the classes it may be of: what its relation takes there, or, if that cannot be told, the class it is of)
  const types = createMemo(() => {
    const offered = describableTypes(definitions, props.option);
    const own = criteria()?.type;
    return offered.length > 0 ? offered : own ? [own] : [];
  });
  const summary = createSummary(criteria);
  // (what the dialog found when Done was last pressed: until the item is saved and read again)
  const [found, setFound] = createSignal<Preview | null>(null);
  const saved = createMemo(() => savedResult(props.value));
  const [open, setOpen] = createSignal(false);
  // (a new one, not given criteria yet: it has nothing to show until it has them)
  const fresh = untrack(() => !id() && !criteria());
  onSettled(() => {
    if (fresh) setOpen(true);
  });
  const done = (given: CriteriaDone) => {
    setOpen(false);
    const changed = !sameCriteria(given.criteria, criteria());
    const was = props.value;
    const next = withCriteria(was, props.model, given.wording, given.criteria);
    // (written part by part at its path, not as a new whole (`onChange`): the list it is in would take a new object
    // for a new item, and draw this card again, without what the dialog found)
    for (const key of Object.keys(was)) if (!(key in next)) form.remove([...props.path, key]);
    form.set([...props.path, "wording"], next.wording);
    form.set([...props.path, "criteria"], next.criteria);
    if (changed || !saved()) setFound(given.preview);
  };
  const cancel = () => {
    setOpen(false);
    // (one that never had criteria is not kept: it would be a description of nothing)
    if (!criteria()) props.onRemove?.();
  };
  const tint = () => kindTint(props.model.kind, props.model.interfaceMeta?.colour) || plainTint;
  const rule = () => kindRule(props.model.kind, props.model.interfaceMeta?.colour);
  const editName = () => t("criteria_edit", "Edit the criteria");
  return (
    <div class="flex w-full min-w-0 scroll-mt-28 flex-col" data-item-id={id()} data-testid="criteria-editor">
      {/* (a bar of one height, as tall as a chip and its frame, so that its buttons can be as wide as it is tall) */}
      <div class={[headBarClass, "h-9"]}>
        <span data-type-info={props.type} data-tint class={[typeChipClass, tint(), rule()]}>
          {modelName(props.type)}
        </span>
        <div class="flex min-w-0 flex-1 items-stretch overflow-hidden rounded-r-xs border-[0.5px] border-l-0 border-slate-400/70">
          <div class="flex min-w-0 flex-1 items-center overflow-hidden px-2 whitespace-nowrap">
            <Show
              when={criteria()}
              fallback={<span class="text-sm text-slate-500 italic">{t("criteria_no_criteria", "No criteria yet")}</span>}
            >
              <CriteriaSummary parts={summary.parts()} labels={summary.labels()} />
            </Show>
          </div>
          <button
            type="button"
            class={[BAR_BUTTON, "text-slate-600 hover:bg-slate-400/30"]}
            aria-label={editName()}
            title={editName()}
            onClick={() => setOpen(true)}
          >
            <PencilIcon />
          </button>
          <Show when={props.onRemove}>
            {(onRemove) => (
              <button
                type="button"
                class={[BAR_BUTTON, "text-red-800 hover:bg-red-400/30"]}
                aria-label={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
                title={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
                onClick={() => onRemove()()}
              >
                ✕
              </button>
            )}
          </Show>
        </div>
      </div>
      <Show when={criteria()}>
        <div class={["ml-2 pt-3", nestedClass, rule()]}>
          <Show when={wording()}>
            <p class="text-sm text-slate-700" data-testid="criteria-wording">
              {t("criteria_quoted", "“{wording}”", { wording: wording() })}
            </p>
          </Show>
          <Show when={summary.missing().length > 0}>
            <p class="text-xs text-red-800" data-testid="criteria-names-deleted">
              {t("criteria_names_deleted", "Names a deleted entity")}
            </p>
          </Show>
          <Show
            when={found()}
            fallback={
              <Show when={saved()}>
                {(result) => (
                  <PreviewResult count={result().count} tooBroad={result().count > result().candidates.length} candidates={result().candidates} />
                )}
              </Show>
            }
          >
            {(preview) => (
              <PreviewResult
                count={preview().count}
                tooBroad={preview().tooBroad}
                candidates={preview().candidates}
                note={t("criteria_not_saved", "not saved yet")}
              />
            )}
          </Show>
        </div>
      </Show>
      <Show when={open()}>
        <CriteriaDialog
          types={types()}
          value={{ wording: wording(), criteria: criteria() }}
          named={() => namedIds(definitions, form.plain())}
          onDone={done}
          onCancel={cancel}
        />
      </Show>
    </div>
  );
}
