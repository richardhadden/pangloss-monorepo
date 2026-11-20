// (what the dialog of a description and the form of a shared description both edit criteria with: the search form of
// the class, what it cannot show, and what the criteria find)
import {
  ApiError,
  buttonClass,
  compileSearch,
  pickedIds,
  references,
  SearchFields,
  useApi,
  useModels,
  useTranslations,
  whereToForm,
  withLabels,
} from "@pangloss/interface-core";
import type { ModelDefinitions, NodeSearch } from "@pangloss/interface-core";
import { createMemo, createSignal, Loading, onSettled, Show, untrack } from "solid-js";
import type { Accessor } from "solid-js";
import { preview } from "../api";
import type { Criteria, Preview } from "../api";
import { brokenField } from "../value";
import type { Broken } from "../value";
import { PreviewResult } from "./Candidates";
import { createSummary, CriteriaSummary } from "./CriteriaSummary";
import { labelClass } from "./parts";
import { SharedSummary } from "./Shared";

/** What the criteria were last found to find, as it is being asked */
export type Result =
  | { state: "none" }
  | { state: "asking"; last?: Preview }
  | { state: "found"; preview: Preview }
  | { state: "refused"; detail: string };


/** The form of a stored pattern, or `null` if the form cannot show it (also when the models no longer fit it at all) */
function formOf(definitions: ModelDefinitions, type: string, where: Record<string, unknown>): NodeSearch | null {
  try {
    return whereToForm(definitions, type, where);
  } catch {
    return null;
  }
}

export interface CriteriaEditingOptions {
  /** The class described */
  type: string;
  /** What the form starts with (of that class) */
  start: Criteria | null;
  /** The criteria are out of date: why (the row of the field that failed is red), and since when */
  broken?: Broken | null;
  /** The ids of the entities the document names, which are never its candidates (what the preview leaves out) */
  named: () => string[];
  /**
   * The shared description the criteria are added to (its id): what is asked about is what both find, and the
   * criteria may have no condition
   */
  shared?: string | null;
  /** Called with the criteria as they are after each change of the form (`null`: no condition) */
  onChange?: (criteria: Criteria | null) => void;
  /** Called when what the criteria find is asked about: as the dialog opens, and a moment after each change */
  onAsk?: (criteria: Criteria | null) => void;
}

/**
 * The criteria of one class being edited: the form they start with (read once: what is edited from then on is the
 * form's own), what they are now (`where`), and what they find, asked as they are given and a moment after each
 * change of the form (`POST /api/criteria/preview`; an answer to an ask that is not the last is not shown). Criteria
 * that are out of date are not asked about (the server refuses them, for the reason the notice gives), and are
 * `blocked` until they are changed: saved as they are, they would be refused again
 */
export function createCriteriaEditing(options: CriteriaEditingOptions) {
  const api = useApi();
  const definitions = useModels();
  const type = options.type;
  const start = options.start;
  const broken = options.broken ?? null;
  const shared = options.shared ?? null;
  // (the form of what was there; `null`: the form cannot show it)
  // (read once, on purpose: the stored criteria may be of the form's store, and what is edited is the form's own)
  const form: NodeSearch | null = untrack(() => (start ? formOf(definitions, type, start.where ?? {}) : { type }));
  // (the field of the root whose condition failed, if the reason names one)
  const failed = broken ? [brokenField(broken.reason)].filter((name): name is string => name !== null) : [];
  // (out of date: changed since it was opened, so that what is given now may be saved)
  const [edited, setEdited] = createSignal(false);
  const [where, setWhere] = createSignal<Record<string, unknown> | undefined>(
    untrack(() => (start && Object.keys(start.where ?? {}).length > 0 ? (start.where ?? undefined) : undefined)),
  );
  const [result, setResult] = createSignal<Result>({ state: "none" });
  const criteria = (): Criteria | null => {
    const now = where();
    return now ? { type, where: now } : null;
  };
  const summary = createSummary(criteria, () => shared !== null);

  let asked = 0;
  const ask = (now: Record<string, unknown> | undefined) => {
    const number = ++asked;
    options.onAsk?.(now ? { type, where: now } : null);
    // (without a condition there is nothing to ask about, unless they are added to a shared description)
    if (!now && !shared) {
      setResult({ state: "none" });
      return;
    }
    const before = untrack(result);
    setResult({ state: "asking", last: before.state === "found" ? before.preview : before.state === "asking" ? before.last : undefined });
    preview(api, { type, where: now ?? {} }, options.named(), shared).then(
      (found) => {
        if (number === asked) setResult({ state: "found", preview: found });
      },
      (error: unknown) => {
        if (number !== asked) return;
        setResult({ state: "refused", detail: error instanceof ApiError ? error.detail : String(error) });
      },
    );
  };
  onSettled(() => {
    if (!broken) untrack(() => ask(where()));
  });
  const changed = (next: NodeSearch) => {
    const now = compileSearch(next);
    setWhere(now);
    setEdited(true);
    options.onChange?.(now ? { type, where: now } : null);
    ask(now);
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
  return {
    type,
    start,
    broken,
    shared,
    form,
    failed,
    where,
    criteria,
    result,
    summary,
    changed,
    initial,
    /** Out-of-date criteria not yet changed */
    blocked: () => broken !== null && !edited(),
    /** What they find, as last found (while the next answer is asked for, the last one) */
    shownPreview: (): Preview | undefined => {
      const now = result();
      return now.state === "found" ? now.preview : now.state === "asking" ? now.last : undefined;
    },
    /** What they were found to find, if the answer to the last ask has come */
    found: (): Preview | null => {
      const now = result();
      return now.state === "found" ? now.preview : null;
    },
  };
}

export type CriteriaEditing = ReturnType<typeof createCriteriaEditing>;

/**
 * The search form of the class (`SearchFields`, without Order by), headed "Criteria: {type}" (or `heading`), with
 * Back (`onBack`: another class). Criteria the form cannot show are shown as they are stored, read only, with "Start
 * afresh" (`onAfresh`) if they are out of date
 */
export function CriteriaFields(props: { editing: CriteriaEditing; heading?: string; onBack?: () => void; onAfresh?: () => void }) {
  const { t, modelName } = useTranslations();
  const editing = untrack(() => props.editing);
  return (
    <section class="flex flex-col gap-2" aria-label={t("criteria_criteria", "Criteria")}>
      <div class="flex items-center gap-2">
        <span class={labelClass}>{props.heading ?? t("criteria_criteria_of", "Criteria: {type}", { type: modelName(editing.type) })}</span>
        <Show when={props.onBack}>
          <button type="button" class={buttonClass("quiet")} onClick={() => props.onBack?.()}>
            {t("back", "Back")}
          </button>
        </Show>
      </div>
      <Show
        when={editing.form}
        fallback={
          <div class="flex flex-col gap-2" data-testid="criteria-read-only">
            <p class="text-sm text-slate-700">
              <Show
                when={editing.broken}
                fallback={t(
                  "criteria_read_only",
                  "These criteria were written with something the form cannot show. They are shown as they are, and only the wording can be changed here.",
                )}
              >
                {t(
                  "criteria_read_only_broken",
                  "The form can no longer show these criteria: they name what the models no longer have. They are shown as they were stored. Start afresh to write them again.",
                )}
              </Show>
            </p>
            <pre class="max-h-64 overflow-auto rounded-xs border-[0.5px] border-slate-400/70 bg-slate-50 p-2 text-xs">
              {JSON.stringify(editing.start, null, 2)}
            </pre>
            <Show when={editing.broken && props.onAfresh}>
              <div>
                <button
                  type="button"
                  class={buttonClass("ordinary", "sm")}
                  data-testid="criteria-start-afresh"
                  onClick={() => props.onAfresh?.()}
                >
                  {t("criteria_start_afresh", "Start afresh")}
                </button>
              </div>
            </Show>
          </div>
        }
      >
        <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
          <Show when={editing.initial()}>
            {(given) => <SearchFields type={editing.type} order={false} initial={given()} onChange={editing.changed} invalid={editing.failed} />}
          </Show>
        </Loading>
      </Show>
    </section>
  );
}

/**
 * What the criteria find: their summary (with `shared`, the shared description they are added to, then these), why
 * the server refuses them, and up to five chips and the count (the last answer faded while the next is asked for).
 * Without a condition (and no shared description), a hint that one is needed
 */
export function CriteriaResult(props: { editing: CriteriaEditing; shared?: { id: string; label: string } | null; hint?: string }) {
  const { t } = useTranslations();
  const editing = untrack(() => props.editing);
  const result: Accessor<Result> = editing.result;
  return (
    <section
      class="flex flex-col gap-2 border-t-[0.5px] border-slate-400/50 pt-4"
      aria-label={t("criteria_result", "What they find")}
      data-testid="criteria-result"
    >
      <Show
        when={editing.where() || editing.shared}
        fallback={
          <p class="text-sm text-slate-500" data-testid="criteria-need-condition">
            {props.hint ?? t("criteria_need_condition", "Add at least one condition: a description is saved with its criteria.")}
          </p>
        }
      >
        <Show when={props.shared} fallback={<CriteriaSummary parts={editing.summary.parts()} labels={editing.summary.labels()} full />}>
          {(shared) => <SharedSummary shared={shared()} parts={editing.summary.parts()} labels={editing.summary.labels()} full />}
        </Show>
        <Show when={result().state === "refused" && (result() as { detail: string }).detail}>
          {(detail) => (
            <p class="text-sm text-red-800" role="alert" data-testid="criteria-refused">
              {detail()}
            </p>
          )}
        </Show>
        {/* (while the next answer is asked for, the last one stays, faded) */}
        <Show
          when={editing.shownPreview()}
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
  );
}
