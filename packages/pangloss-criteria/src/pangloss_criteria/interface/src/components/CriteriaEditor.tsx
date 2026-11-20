import {
  fieldGridClass,
  FieldRow,
  headBarClass,
  inputClass,
  kindRule,
  kindTint,
  nestedClass,
  plainTint,
  typeChipClass,
  useItemForm,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import type { EditCardProps, ItemFormState } from "@pangloss/interface-core";
import { createMemo, createSignal, onSettled, Show, untrack } from "solid-js";
import type { JSX } from "@solidjs/web";
import type { Criteria, Preview } from "../api";
import { holderOf, isBare, markOf, newMark, placesIn, placesOf, sameOneChoices, samePath } from "../same";
import type { Place } from "../same";
import { computedKeys, criteriaOf, describableTypes, namedIds, sameCriteria, savedResult, withCriteria, wordingOf } from "../value";
import { PreviewResult } from "./Candidates";
import { CriteriaDialog } from "./CriteriaDialog";
import type { CriteriaDone, SameOneChoice } from "./CriteriaDialog";
import { createSummary, CriteriaSummary } from "./CriteriaSummary";
import { BAR_BUTTON, BAR_WORD_BUTTON, PencilIcon } from "./parts";

/** A copy of criteria to write into the form (an object of the form's store written at a second path would be one object at both) */
const copied = (criteria: Criteria): Criteria => JSON.parse(JSON.stringify({ type: criteria.type, where: criteria.where ?? {} })) as Criteria;

/**
 * Writes `criteria` into the description at `path`, part by part; what the server worked out of other criteria goes.
 * (At its path, not as a new whole: the list it is in would take a new object for a new item)
 */
function writeCriteria(form: ItemFormState, place: Place, keys: string[], criteria: Criteria | null) {
  if (!sameCriteria(place.criteria, criteria)) for (const key of keys) if (key in place.value) form.remove([...place.path, key]);
  form.set([...place.path, "criteria"], criteria === null ? null : copied(criteria));
}

/**
 * A description (`MatchesCriteria`) in a form, in place of the box a reified relation has. One that holds criteria is
 * `OwnCriteria`; one that is the same one as another place of the document (its mark, `sameOne`, and no criteria of
 * its own) is `SameAsAnother`.
 *
 * It writes only what a description is written with (its `wording`, `criteria` and mark) and keeps what the read gave;
 * when the criteria change, what the server worked out of the old ones goes (`withCriteria`).
 */
export default function CriteriaEditor(props: EditCardProps) {
  return (
    <Show when={isBare(props.value)} fallback={<OwnCriteria {...props} />}>
      <SameAsAnother {...props} />
    </Show>
  );
}

/** The places of the form's document, as it is now (a plain copy: not followed) */
function usePlaces(props: EditCardProps) {
  const form = useItemForm();
  const definitions = useModels();
  const { fieldName } = useTranslations();
  return {
    now: () => placesIn(definitions, form.plain(), props.type, fieldName),
    /** (followed: every change of the form) */
    followed: () => placesIn(definitions, form.get([]), props.type, fieldName),
  };
}

/** The head bar of a description in a form: its type, then what `children` draws, and the buttons */
function Bar(props: EditCardProps & { first?: JSX.Element; children: JSX.Element; onEdit?: () => void; onRemove?: () => void }) {
  const { t, modelName } = useTranslations();
  const tint = () => kindTint(props.model.kind, props.model.interfaceMeta?.colour) || plainTint;
  const rule = () => kindRule(props.model.kind, props.model.interfaceMeta?.colour);
  const editName = () => t("criteria_edit", "Edit the criteria");
  return (
    // (a bar of one height, as tall as a chip and its frame, so that its buttons can be as wide as it is tall)
    <div class={[headBarClass, "h-9"]}>
      <span data-type-info={props.type} data-tint class={[typeChipClass, tint(), rule()]}>
        {modelName(props.type)}
      </span>
      <div class="flex min-w-0 flex-1 items-stretch overflow-hidden rounded-r-xs border-[0.5px] border-l-0 border-slate-400/70">
        {props.first}
        <div class="flex min-w-0 flex-1 items-center overflow-hidden px-2 whitespace-nowrap">{props.children}</div>
        <Show when={props.onEdit}>
          {(onEdit) => (
            <button
              type="button"
              class={[BAR_BUTTON, "text-slate-600 hover:bg-slate-400/30"]}
              aria-label={editName()}
              title={editName()}
              onClick={() => onEdit()()}
            >
              <PencilIcon />
            </button>
          )}
        </Show>
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
  );
}

/**
 * A description that holds its criteria: the summary of its criteria, a pencil that opens them in a dialog
 * (`CriteriaDialog`) and ✕; under it the wording, and what the criteria find. What the dialog last found is shown as
 * not saved yet; a saved description that has not been changed shows what the server found. A new one (just added)
 * opens the dialog at once, and Cancel there takes it out again, as it never had criteria; the dialog offers it first
 * to be "the same one as" another description of the document whose class this field takes. Changed criteria are
 * written into every place of its mark that holds criteria too (they must be the same); removed while other places of
 * its mark hold none, it gives its criteria to the first of them.
 */
function OwnCriteria(props: EditCardProps) {
  const form = useItemForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const places = usePlaces(props);
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
  const fresh = untrack(() => !id() && !criteria() && !markOf(props.value));
  // (what a new one may be the same one as: the other descriptions of the document when it was added)
  const choices: SameOneChoice[] = fresh
    ? untrack(() =>
        sameOneChoices(places.now(), types(), props.path).map((place) => ({
          value: JSON.stringify(place.path),
          criteria: place.criteria!,
          wording: wordingOf(place.value),
          field: place.field,
        })),
      )
    : [];
  onSettled(() => {
    if (fresh) setOpen(true);
  });
  const keys = () => computedKeys(props.model);
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
    // (the other places of its mark that hold criteria hold the same)
    const mark = markOf(was);
    if (changed && mark)
      for (const place of placesOf(places.now(), mark))
        if (place.criteria !== null && !samePath(place.path, props.path)) writeCriteria(form, place, keys(), given.criteria);
    if (changed || !saved()) setFound(given.preview);
  };
  const cancel = () => {
    setOpen(false);
    // (one that never had criteria is not kept: it would be a description of nothing)
    if (!criteria()) props.onRemove?.();
  };
  // (this place is the same one as the one chosen: it takes the mark of that one, made now if it has none, and holds
  // no criteria. The card is then `SameAsAnother`)
  const sameAs = (value: string, said: string) => {
    const holder = places.now().find((place) => JSON.stringify(place.path) === value);
    if (!holder) return;
    setOpen(false);
    const here = [...props.path];
    let mark = holder.mark;
    if (mark === null) {
      mark = newMark();
      form.set([...holder.path, "sameOne"], mark);
    }
    for (const key of keys()) if (key in props.value) form.remove([...here, key]);
    form.set([...here, "wording"], said.trim() === "" ? null : said);
    form.set([...here, "criteria"], null);
    form.set([...here, "sameOne"], mark);
  };
  const remove = () => {
    const mark = markOf(props.value);
    const own = criteria();
    if (mark && own) {
      const others = placesOf(places.now(), mark).filter((place) => !samePath(place.path, props.path));
      // (the last that holds the criteria: the next place of its mark takes them, or none would say who it is)
      if (others.length > 0 && others.every((place) => place.criteria === null)) writeCriteria(form, others[0]!, keys(), own);
    }
    props.onRemove?.();
  };
  const rule = () => kindRule(props.model.kind, props.model.interfaceMeta?.colour);
  return (
    <div class="flex w-full min-w-0 scroll-mt-28 flex-col" data-item-id={id()} data-testid="criteria-editor">
      <Bar {...props} onEdit={() => setOpen(true)} onRemove={props.onRemove ? remove : undefined}>
        <Show
          when={criteria()}
          fallback={<span class="text-sm text-slate-500 italic">{t("criteria_no_criteria", "No criteria yet")}</span>}
        >
          <CriteriaSummary parts={summary.parts()} labels={summary.labels()} />
        </Show>
      </Bar>
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
          sameOne={choices.length > 0 ? { choices, onChoose: sameAs } : undefined}
        />
      </Show>
    </div>
  );
}

/**
 * A place that is the same one as another of the document (its mark, and no criteria): "The same one as" and the
 * summary of the criteria of the place of its mark that holds them, found in the form; its own wording. The pencil
 * opens those criteria and writes them there (in every place of the mark that holds them). "Describe separately" makes
 * it a description of its own, with a copy of those criteria. With no place in the form that holds them it says so,
 * and can be removed
 */
function SameAsAnother(props: EditCardProps) {
  const form = useItemForm();
  const definitions = useModels();
  const { t, fieldName } = useTranslations();
  const places = usePlaces(props);
  const mark = () => markOf(props.value);
  const id = () => (typeof props.value.id === "string" ? props.value.id : undefined);
  const holder = createMemo(() => holderOf(places.followed(), mark()));
  // (a plain copy, not the form's own object: what the dialog makes of it is not to follow the form; the same while
  // the criteria are the same, whatever else in the form changes)
  const held = createMemo(
    () => {
      const criteria = holder()?.criteria;
      return criteria ? copied(criteria) : null;
    },
    { equals: sameCriteria },
  );
  const summary = createSummary(held);
  const [open, setOpen] = createSignal(false);
  const keys = () => computedKeys(props.model);
  const done = (given: CriteriaDone) => {
    setOpen(false);
    for (const place of placesOf(places.now(), mark())) if (place.criteria !== null) writeCriteria(form, place, keys(), given.criteria);
  };
  const separately = () => {
    const criteria = untrack(held);
    if (!criteria) return;
    const here = [...props.path];
    form.set([...here, "sameOne"], null);
    form.set([...here, "criteria"], copied(criteria));
  };
  // (the reader's own once it is drawn: see the skill's note on boxes)
  const startingWording = untrack(() => wordingOf(props.value));
  const wordingName = () => fieldName("MatchesCriteria", "wording");
  const rule = () => kindRule(props.model.kind, props.model.interfaceMeta?.colour);
  const separateName = () => t("criteria_describe_separately", "Describe separately");
  return (
    <div class="flex w-full min-w-0 scroll-mt-28 flex-col" data-item-id={id()} data-testid="criteria-editor">
      <Bar
        {...props}
        first={
          <Show when={held()}>
            <button
              type="button"
              class={[BAR_WORD_BUTTON, "text-slate-700 hover:bg-slate-400/30"]}
              title={t("criteria_describe_separately_hint", "Give this place criteria of its own, a copy of these: it is no longer said to be the same one")}
              onClick={separately}
            >
              {separateName()}
            </button>
          </Show>
        }
        onEdit={held() ? () => setOpen(true) : undefined}
      >
        <span class="mr-2 shrink-0 text-xs font-semibold text-slate-500 uppercase select-none" data-testid="criteria-same-one-mark">
          {t("criteria_same_one_as", "The same one as")}
        </span>
        <Show
          when={held()}
          fallback={
            <span class="truncate text-sm text-red-800" data-testid="criteria-same-one-missing">
              {t("criteria_same_one_missing", "No description in this form holds the criteria")}
            </span>
          }
        >
          <CriteriaSummary parts={summary.parts()} labels={summary.labels()} />
        </Show>
      </Bar>
      <div class={["ml-2 pt-3", nestedClass, rule()]}>
        <dl class={fieldGridClass}>
          <FieldRow name={wordingName()} path={[...props.path, "wording"]}>
            <input
              class={inputClass}
              aria-label={wordingName()}
              placeholder={t("criteria_wording_placeholder", "N. N., the duke's secretary")}
              value={startingWording}
              onInput={(event) => {
                const said = event.currentTarget.value;
                form.set([...props.path, "wording"], said.trim() === "" ? null : said);
              }}
            />
          </FieldRow>
        </dl>
      </div>
      <Show when={open() && held()}>
        {(criteria) => (
          <CriteriaDialog
            types={[criteria().type]}
            value={{ wording: "", criteria: criteria() }}
            named={() => namedIds(definitions, form.plain())}
            onDone={done}
            onCancel={() => setOpen(false)}
            withoutWording
          />
        )}
      </Show>
    </div>
  );
}
