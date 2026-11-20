import {
  ApiError,
  buttonClass,
  compileSearch,
  inputClass,
  menuGroups,
  MenuSelect,
  pickedIds,
  references,
  SearchFields,
  TypeGrid,
  useApi,
  useComponent,
  useModels,
  useTranslations,
  whereToForm,
  withLabels,
} from "@pangloss/interface-core";
import type { NodeSearch } from "@pangloss/interface-core";
import { createMemo, createSignal, Loading, onSettled, Show, untrack } from "solid-js";
import { preview } from "../api";
import type { Criteria, Preview } from "../api";
import { describeCriteria, describeText, idsOf } from "../describe";
import { createLabels } from "../labels";
import { PreviewResult } from "./Candidates";
import { createSummary, CriteriaSummary } from "./CriteriaSummary";

/** What a description holds that the dialog edits */
export interface CriteriaValue {
  wording: string;
  criteria: Criteria | null;
}

/** What Done gives: the wording, the criteria, and what they were last found to find (for the closed card) */
export interface CriteriaDone {
  wording: string;
  criteria: Criteria;
  preview: Preview | null;
}

/** Another description of the document, which a new one may say it is the same one as */
export interface SameOneChoice {
  /** What names it to the one who offers it (its path in the form) */
  value: string;
  criteria: Criteria;
  wording: string;
  /** The name of the field it is in */
  field: string;
}

export interface CriteriaDialogProps {
  /** The entity classes the description may be of (those its relation takes there); chosen first if there are several */
  types: string[];
  value: CriteriaValue;
  /** The ids of the entities the document names, which are never its candidates (what the preview leaves out) */
  named: () => string[];
  onDone: (done: CriteriaDone) => void;
  onCancel: () => void;
  /**
   * (a new description) The others of the document it may be the same one as: offered first, "The same one as";
   * choosing one gives its `value` and the wording written so far
   */
  sameOne?: { choices: SameOneChoice[]; onChoose: (value: string, wording: string) => void };
  /** No box for the wording: the criteria of another place are edited, and the wording is its own */
  withoutWording?: boolean;
}

type Result =
  | { state: "none" }
  | { state: "asking"; last?: Preview }
  | { state: "found"; preview: Preview }
  | { state: "refused"; detail: string };

const labelClass = "text-xs font-semibold text-slate-500 uppercase";

/**
 * The criteria of a description, in a dialog: which class it is of (a `TypeGrid` of `types`, skipped when there is one),
 * what the source says (`wording`), and the search form of the class (`SearchFields`, without Order by). What the
 * criteria find now is asked after each change of the form (`POST /api/criteria/preview`; a later answer replaces an
 * earlier, and one that comes after it is not shown): up to five chips and the count. Done gives the wording and the
 * criteria; without a condition there is nothing to save, and Done is off. Criteria the form cannot show (written in
 * Python with something it lacks) are shown as they are, and only the wording can be changed.
 */
export function CriteriaDialog(props: CriteriaDialogProps) {
  const Modal = useComponent("Modal");
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const start = untrack(() => props.value);
  const types = () => props.types;
  const [type, setType] = createSignal<string | undefined>(
    untrack(() => start.criteria?.type ?? (types().length === 1 ? types()[0] : undefined)),
  );
  const [wording, setWording] = createSignal(start.wording);
  const groups = createMemo(() => menuGroups(definitions, types().map((name) => ({ kind: "entity" as const, type: name, edgeModel: null }))));
  // (the reader's own once it is drawn: see the skill's note on boxes)
  const startingWording = start.wording;
  return (
    <Modal title={modelName("MatchesCriteria")} onClose={props.onCancel} size="xl">
      <div class="flex min-h-0 flex-col gap-5 overflow-y-auto p-4" data-testid="criteria-dialog">
        <Show when={props.sameOne && props.sameOne.choices.length > 0 && props.sameOne}>
          {(same) => <SameOne choices={same().choices} onChoose={(value) => same().onChoose(value, untrack(wording))} />}
        </Show>
        <Show when={!props.withoutWording}>
          <label class="flex flex-col gap-1">
            <span class={labelClass}>{t("criteria_wording", "What the source says")}</span>
            <input
              class={inputClass}
              aria-label={t("criteria_wording", "What the source says")}
              placeholder={t("criteria_wording_placeholder", "N. N., the duke's secretary")}
              value={startingWording}
              onInput={(event) => setWording(event.currentTarget.value)}
            />
          </label>
        </Show>
        <Show
          when={type()}
          fallback={
            <div class="flex flex-col gap-2">
              <span class={labelClass}>{t("criteria_choose_type", "What is described")}</span>
              <div class="overflow-hidden rounded-xs border-[0.5px] border-dashed border-slate-400/80 bg-white/60">
                <TypeGrid groups={groups()} onChoose={(choice) => setType(choice.type)} autofocus />
              </div>
              <div class="flex justify-end">
                <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onCancel()}>
                  {t("cancel", "Cancel")}
                </button>
              </div>
            </div>
          }
        >
          {(chosen) => (
            <Pattern
              type={chosen()}
              // (what was there is shown only for the class it is of: another class starts with nothing)
              criteria={start.criteria?.type === chosen() ? start.criteria : null}
              wording={wording}
              named={props.named}
              onBack={types().length > 1 ? () => setType(undefined) : undefined}
              onDone={props.onDone}
              onCancel={props.onCancel}
            />
          )}
        </Show>
      </div>
    </Modal>
  );
}

/**
 * "The same one as": a menu of the other descriptions of the document (each by the summary of its criteria and its
 * wording, under the name of the field it is in). Choosing one says that this place describes the same one
 */
function SameOne(props: { choices: SameOneChoice[]; onChoose: (value: string) => void }) {
  const definitions = useModels();
  const words = useTranslations();
  const { t } = words;
  const parts = createMemo(() => props.choices.map((choice) => describeCriteria(choice.criteria, words, definitions)));
  // (the entities they name, by their labels: one request for all of them)
  const labels = createLabels(() => parts().flatMap(idsOf));
  const options = createMemo(() =>
    props.choices.map((choice, index) => {
      const summary = describeText(parts()[index] ?? [], labels(), t("criteria_deleted_entity", "deleted entity"));
      return {
        value: choice.value,
        label: choice.wording.trim() === "" ? summary : `${summary} · ${t("criteria_quoted", "“{wording}”", { wording: choice.wording })}`,
        group: choice.field || undefined,
      };
    }),
  );
  return (
    <div class="flex flex-col gap-1 border-b-[0.5px] border-slate-400/50 pb-4" data-testid="criteria-same-one">
      <span class={labelClass}>{t("criteria_same_one_as", "The same one as")}</span>
      <MenuSelect
        label={t("criteria_same_one_as", "The same one as")}
        placeholder={t("criteria_same_one_placeholder", "Another description in this document…")}
        options={options()}
        class="w-full"
        onChoose={props.onChoose}
      />
      <p class="text-xs text-slate-500">
        {t("criteria_same_one_hint", "Or write criteria of its own below: two descriptions with equal criteria are not taken to be one.")}
      </p>
    </div>
  );
}

/** The criteria of one class: its search form (or what the form cannot show), what they find, and the buttons */
function Pattern(props: {
  type: string;
  criteria: Criteria | null;
  wording: () => string;
  named: () => string[];
  onBack?: () => void;
  onDone: (done: CriteriaDone) => void;
  onCancel: () => void;
}) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const type = untrack(() => props.type);
  const start = untrack(() => props.criteria);
  // (the form of what was there; `null`: the form cannot show it)
  const form: NodeSearch | null = start ? whereToForm(definitions, type, start.where ?? {}) : { type };
  const [where, setWhere] = createSignal<Record<string, unknown> | undefined>(
    start && Object.keys(start.where ?? {}).length > 0 ? (start.where ?? undefined) : undefined,
  );
  const [result, setResult] = createSignal<Result>({ state: "none" });
  const summary = createSummary(() => {
    const now = where();
    return now ? { type, where: now } : null;
  });

  // What the criteria find now. (Each ask has a number: an answer to one that is not the last is not shown)
  let asked = 0;
  const ask = (now: Record<string, unknown> | undefined) => {
    const number = ++asked;
    if (!now) {
      setResult({ state: "none" });
      return;
    }
    const before = result();
    setResult({ state: "asking", last: before.state === "found" ? before.preview : before.state === "asking" ? before.last : undefined });
    preview(api, { type, where: now }, props.named()).then(
      (found) => {
        if (number === asked) setResult({ state: "found", preview: found });
      },
      (error: unknown) => {
        if (number !== asked) return;
        setResult({ state: "refused", detail: error instanceof ApiError ? error.detail : String(error) });
      },
    );
  };
  // (what was there is asked about once the dialog is open)
  onSettled(() => {
    untrack(() => ask(where()));
  });
  const changed = (next: NodeSearch) => {
    const now = compileSearch(next);
    setWhere(now);
    ask(now);
  };
  const shownPreview = (): Preview | undefined => {
    const now = result();
    return now.state === "found" ? now.preview : now.state === "asking" ? now.last : undefined;
  };
  const done = () => {
    const now = where();
    if (!now) return;
    const found = result();
    props.onDone({
      wording: props.wording(),
      criteria: { type, where: now },
      preview: found.state === "found" ? found.preview : null,
    });
  };
  // (the form starts with the labels of the entities it names, which only the API knows)
  const initial = createMemo(async () => {
    if (!form) return null;
    const ids = pickedIds(form);
    if (ids.length === 0) return form;
    // (if they cannot be had, the form is shown without them: each entity as "deleted", which saving keeps as it is)
    const found = await references(api, ids).catch(() => []);
    return withLabels(form, found);
  });
  return (
    <>
      <section class="flex flex-col gap-2" aria-label={t("criteria_criteria", "Criteria")}>
        <div class="flex items-center gap-2">
          <span class={labelClass}>
            {t("criteria_criteria_of", "Criteria: {type}", { type: modelName(type) })}
          </span>
          <Show when={props.onBack}>
            <button type="button" class={buttonClass("quiet")} onClick={() => props.onBack?.()}>
              {t("back", "Back")}
            </button>
          </Show>
        </div>
        <Show
          when={form}
          fallback={
            <div class="flex flex-col gap-2" data-testid="criteria-read-only">
              <p class="text-sm text-slate-700">
                {t(
                  "criteria_read_only",
                  "These criteria were written with something the form cannot show. They are shown as they are, and only the wording can be changed here.",
                )}
              </p>
              <pre class="max-h-64 overflow-auto rounded-xs border-[0.5px] border-slate-400/70 bg-slate-50 p-2 text-xs">
                {JSON.stringify(start, null, 2)}
              </pre>
            </div>
          }
        >
          <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
            <Show when={initial()}>
              {(given) => <SearchFields type={type} order={false} initial={given()} onChange={changed} />}
            </Show>
          </Loading>
        </Show>
      </section>
      <section class="flex flex-col gap-2 border-t-[0.5px] border-slate-400/50 pt-4" aria-label={t("criteria_result", "What they find")} data-testid="criteria-result">
        <Show
          when={where()}
          fallback={
            <p class="text-sm text-slate-500" data-testid="criteria-need-condition">
              {t("criteria_need_condition", "Add at least one condition: a description is saved with its criteria.")}
            </p>
          }
        >
          <CriteriaSummary parts={summary.parts()} labels={summary.labels()} full />
          <Show when={result().state === "refused" && (result() as { detail: string }).detail}>
            {(detail) => (
              <p class="text-sm text-red-800" role="alert" data-testid="criteria-refused">
                {detail()}
              </p>
            )}
          </Show>
          {/* (while the next answer is asked for, the last one stays, faded) */}
          <Show
            when={shownPreview()}
            fallback={
              <Show when={result().state === "asking"}>
                <p class="text-xs text-slate-500">{t("criteria_finding", "Finding candidates…")}</p>
              </Show>
            }
          >
            {(found) => (
              <div class={{ "opacity-50": result().state === "asking" }} aria-busy={result().state === "asking" ? "true" : undefined}>
                <PreviewResult count={found().count} tooBroad={found().tooBroad} candidates={found().candidates} />
              </div>
            )}
          </Show>
        </Show>
      </section>
      <div class="flex justify-end gap-2">
        <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onCancel()}>
          {t("cancel", "Cancel")}
        </button>
        <button type="button" class={buttonClass("primary", "md")} disabled={!where()} onClick={done}>
          {t("criteria_done", "Done")}
        </button>
      </div>
    </>
  );
}
