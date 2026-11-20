import {
  buttonClass,
  getItem,
  inputClass,
  menuGroups,
  MenuSelect,
  TypeGrid,
  useApi,
  useComponent,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import { createMemo, createSignal, Errored, Loading, Show, untrack } from "solid-js";
import type { JSX } from "@solidjs/web";
import { similarCriteria } from "../api";
import type { Criteria, Preview, Shared, ShareResult, Similar } from "../api";
import { conditionsOnly, describeCriteria, describeText, idsOf } from "../describe";
import { createLabels } from "../labels";
import { criteriaOf, DESCRIPTION } from "../value";
import type { Broken } from "../value";
import { createCriteriaEditing, CriteriaFields, CriteriaResult } from "./CriteriaForm";
import { labelClass } from "./parts";
import { ShareOffer, SharedHead, StartFrom } from "./Shared";

/** What a description holds that the dialog edits */
export interface CriteriaValue {
  wording: string;
  /** Its own criteria (beside those of the shared description it cites, if it cites one) */
  criteria: Criteria | null;
  /** The criteria are out of date (they no longer fit the models): why, and since which migration */
  broken?: Broken | null;
  /** The shared description it cites (its criteria, when they are known; the dialog reads them otherwise) */
  shared?: { id: string; label: string; criteria?: Criteria | null } | null;
}

/**
 * What Done gives: the wording, the criteria, the shared description it cites, and what they were last found to find
 * (for the closed card). `criteria` may be `null` only with `shared`: conditions of its own beside the shared ones
 */
export interface CriteriaDone {
  wording: string;
  criteria: Criteria | null;
  shared: { id: string; label: string } | null;
  preview: Preview | null;
}

/** Another description of the document, which a new one may say it is the same one as */
export interface SameOneChoice {
  /** What names it to the one who offers it (its path in the form) */
  value: string;
  /** Its own criteria (none: it cites `cited` alone) */
  criteria: Criteria | null;
  /** The label of the shared description it cites, if it cites one */
  cited?: string | null;
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
  /** The id of the document being edited, if it is saved: not counted among the others with the same criteria */
  except?: string | null;
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

/** What the dialog is at: the class, what the form starts with, and the shared description cited, if one is */
interface Stage {
  type: string | undefined;
  start: Criteria | null;
  broken: Broken | null;
  /** (Use) The shared description the mention cites; its criteria `undefined` while they are not known */
  shared: { id: string; label: string; criteria?: Criteria | null } | null;
  /** (just made of these criteria) What making it did */
  made?: ShareResult | null;
}

/**
 * The criteria of a description, in a dialog: which class it is of (a `TypeGrid` of `types`, skipped when there is one),
 * what the source says (`wording`), and the search form of the class (`SearchFields`, without Order by). What the
 * criteria find now is asked after each change of the form (`POST /api/criteria/preview`; a later answer replaces an
 * earlier, and one that comes after it is not shown): up to five chips and the count. Done gives the wording and the
 * criteria; without a condition there is nothing to save, and Done is off. Criteria the form cannot show (written in
 * Python with something it lacks) are shown as they are, and only the wording can be changed.
 *
 * "Start from" lists the shared descriptions of the classes it may be of: **Use** one, and the mention cites it (its
 * criteria at the top, read only, and under them the form is for conditions of the mention's own, "and also"; what
 * is asked about is what both find; Done needs no condition of its own; **Stop using** keeps those conditions as the
 * mention's criteria); **Copy** one, and its criteria fill the form as the mention's own. A mention that cites one
 * opens with it. Criteria of its own that other documents use too are offered to be made one shared description
 * (`ShareOffer`, asked a moment after each change, with what they find): the dialog then cites the one made.
 *
 * Criteria that are out of date (`value.broken`: a migration took away something they name) open with a red notice
 * at the top that says why, and in the form as far as it can show them, the row of the condition that failed red.
 * What the form can no longer show is shown as it was stored, and the criteria can be started afresh; until they are
 * changed Done is off (saved as they are, they would be refused again).
 */
export function CriteriaDialog(props: CriteriaDialogProps) {
  const Modal = useComponent("Modal");
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const start = untrack(() => props.value);
  const types = () => props.types;
  const [stage, setStage] = createSignal<Stage>(
    untrack(() => ({
      type: start.criteria?.type ?? start.shared?.criteria?.type ?? (types().length === 1 ? types()[0] : undefined),
      start: start.criteria,
      broken: start.broken ?? null,
      shared: start.shared ?? null,
    })),
  );
  const [wording, setWording] = createSignal(start.wording);
  // (out-of-date criteria put aside: the form starts with nothing, of a class that can still be described)
  const startAfresh = () => {
    const now = untrack(stage).type;
    const fresh = untrack(types).filter((name) => definitions.searchPatterns?.[name] !== undefined);
    setStage({ type: now && fresh.includes(now) ? now : fresh.length === 1 ? fresh[0] : undefined, start: null, broken: null, shared: null });
  };
  const chooseType = (type: string | undefined) => {
    // (what was there is shown only for the class it is of: another class starts with nothing)
    const own = start.criteria?.type === type ? start.criteria : null;
    setStage({ type, start: own, broken: own ? (start.broken ?? null) : null, shared: null });
  };
  const use = (shared: Shared, made?: ShareResult) =>
    setStage({ type: shared.criteria.type, start: null, broken: null, shared, made: made ?? null });
  const copy = (shared: Shared) => setStage({ type: shared.criteria.type, start: shared.criteria, broken: null, shared: null });
  // (the conditions of its own are kept, now its whole criteria)
  const stopUsing = (own: Criteria | null) => setStage({ type: untrack(stage).type, start: own, broken: null, shared: null });
  const groups = createMemo(() => menuGroups(definitions, types().map((name) => ({ kind: "entity" as const, type: name, edgeModel: null }))));
  // (the reader's own once it is drawn: see the skill's note on boxes)
  const startingWording = start.wording;
  return (
    <Modal title={modelName("MatchesCriteria")} onClose={props.onCancel} size="xl">
      <div class="flex min-h-0 flex-col gap-5 overflow-y-auto p-4" data-testid="criteria-dialog">
        <Show when={start.broken}>{(broken) => <BrokenNotice broken={broken()} />}</Show>
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
        <Show when={!stage().shared && types().length > 0}>
          <StartFrom types={types()} onUse={(shared) => use(shared)} onCopy={copy} />
        </Show>
        <Show when={stage()} keyed>
          {(now) => (
            <Show
              when={now.shared}
              fallback={
                <Show
                  when={now.type}
                  fallback={
                    <div class="flex flex-col gap-2">
                      <span class={labelClass}>{t("criteria_choose_type", "What is described")}</span>
                      <div class="overflow-hidden rounded-xs border-[0.5px] border-dashed border-slate-400/80 bg-white/60">
                        <TypeGrid groups={groups()} onChoose={(choice) => chooseType(choice.type)} autofocus />
                      </div>
                      <div class="flex justify-end">
                        <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onCancel()}>
                          {t("cancel", "Cancel")}
                        </button>
                      </div>
                    </div>
                  }
                >
                  {(type) => (
                    <Pattern
                      type={type()}
                      criteria={now.start}
                      broken={now.broken}
                      onAfresh={startAfresh}
                      wording={wording}
                      named={props.named}
                      except={props.except ?? null}
                      onBack={types().length > 1 ? () => chooseType(undefined) : undefined}
                      onDone={props.onDone}
                      onCancel={props.onCancel}
                      onShared={use}
                    />
                  )}
                </Show>
              }
            >
              {(cited) => (
                <WithShared shared={cited()}>
                  {(known) => (
                    <>
                      <SharedHead shared={known} made={now.made} />
                      <Pattern
                        type={known.criteria.type}
                        criteria={now.start}
                        broken={now.broken}
                        onAfresh={startAfresh}
                        shared={known}
                        onStopUsing={stopUsing}
                        wording={wording}
                        named={props.named}
                        except={props.except ?? null}
                        onDone={props.onDone}
                        onCancel={props.onCancel}
                      />
                    </>
                  )}
                </WithShared>
              )}
            </Show>
          )}
        </Show>
      </div>
    </Modal>
  );
}

/**
 * The shared description a mention cites, with its criteria: as given, or read (its page's read, `GET
 * /api/Description/{id}`) when they are not known. One that cannot be read (gone) says so
 */
function WithShared(props: { shared: { id: string; label: string; criteria?: Criteria | null }; children: (shared: Shared) => JSX.Element }) {
  const api = useApi();
  const { t } = useTranslations();
  const given = untrack(() => props.shared);
  const known = createMemo(async (): Promise<Shared | null> => {
    if (given.criteria) return { id: given.id, label: given.label, criteria: given.criteria };
    const read = await getItem(api, DESCRIPTION, given.id, { incomingLimit: 0, extras: false });
    const criteria = criteriaOf(read as Record<string, unknown>);
    return criteria ? { id: given.id, label: typeof read.label === "string" ? read.label : given.label, criteria } : null;
  });
  // (made where it is shown: one node is not in two places)
  const missing = () => <p class="text-sm text-red-800" role="alert" data-testid="criteria-shared-missing">{t("criteria_shared_missing", "The shared description it cites cannot be read.")}</p>;
  return (
    <Errored fallback={missing()}>
      <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
        <Show when={known()} fallback={missing()}>
          {(shared) => <>{props.children(shared())}</>}
        </Show>
      </Loading>
    </Errored>
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
  const parts = createMemo(() =>
    props.choices.map((choice) => {
      const all = describeCriteria(choice.criteria, words, definitions);
      return choice.cited ? conditionsOnly(all) : all;
    }),
  );
  // (the entities they name, by their labels: one request for all of them)
  const labels = createLabels(() => parts().flatMap(idsOf));
  const options = createMemo(() =>
    props.choices.map((choice, index) => {
      const own = describeText(parts()[index] ?? [], labels(), t("criteria_deleted_entity", "deleted entity"));
      const summary = choice.cited ? (own === "" ? choice.cited : `${choice.cited} + ${own}`) : own;
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

/**
 * That the criteria are out of date, at the top of the dialog, in red: since which migration (or only that they are),
 * the reason, and what is to be done
 */
function BrokenNotice(props: { broken: Broken }) {
  const { t } = useTranslations();
  return (
    <div
      role="alert"
      class="flex flex-col gap-1 rounded-xs border-[0.5px] border-red-700/60 bg-red-50 p-3 text-sm text-red-800"
      data-testid="criteria-broken-notice"
    >
      <p class="font-semibold">
        {props.broken.since
          ? t("criteria_broken_since", "Out of date since migration {migration}", { migration: props.broken.since })
          : t("criteria_out_of_date", "Out of date")}
      </p>
      <p class="text-xs" data-testid="criteria-broken-reason">
        {props.broken.reason}
      </p>
      <p class="text-slate-700">
        {t(
          "criteria_broken_explained",
          "These criteria no longer fit the models, and are not evaluated: the candidates are the last that were found. Correct them, then save the document.",
        )}
      </p>
    </div>
  );
}

/**
 * The criteria of one class: its search form (or what the form cannot show), what they find, the offer to share
 * them, and the buttons. With `shared`, they are the mention's own conditions beside those of the shared description
 * it cites ("and also"), and may be none
 */
function Pattern(props: {
  type: string;
  criteria: Criteria | null;
  /** The criteria are out of date: why (the row of the field that failed is red), and since when */
  broken?: Broken | null;
  /** (out of date) Put the criteria aside and start with nothing */
  onAfresh?: () => void;
  /** The shared description cited */
  shared?: Shared;
  /** (with `shared`) Cite it no longer: given the conditions of its own as they are now */
  onStopUsing?: (own: Criteria | null) => void;
  wording: () => string;
  named: () => string[];
  except: string | null;
  onBack?: () => void;
  onDone: (done: CriteriaDone) => void;
  onCancel: () => void;
  /** A shared description was made of these criteria (the offer): the dialog cites it */
  onShared?: (shared: Shared, made: ShareResult) => void;
}) {
  const api = useApi();
  const { t, modelName } = useTranslations();
  const shared = untrack(() => props.shared ?? null);
  const except = untrack(() => props.except);
  // (what other documents use the same criteria: asked with what they find, of criteria of its own alone)
  const [similar, setSimilar] = createSignal<{ criteria: Criteria; found: Similar } | null>(null);
  let askedSimilar = 0;
  const askSimilar = (criteria: Criteria | null) => {
    const number = ++askedSimilar;
    setSimilar(null);
    if (!criteria || shared || !props.onShared) return;
    similarCriteria(api, criteria, null, except).then(
      (found) => {
        if (number === askedSimilar && found.count > 0) setSimilar({ criteria, found });
      },
      () => {
        // (not known: nothing is offered)
      },
    );
  };
  const editing = createCriteriaEditing(
    untrack(() => ({
      type: props.type,
      start: props.criteria,
      broken: props.broken ?? null,
      named: props.named,
      shared: shared?.id ?? null,
      onAsk: askSimilar,
    })),
  );
  const ready = () => (editing.where() !== undefined || shared !== null) && !editing.blocked();
  const done = () => {
    if (!ready()) return;
    props.onDone({
      wording: props.wording(),
      criteria: editing.criteria(),
      shared: shared ? { id: shared.id, label: shared.label } : null,
      preview: editing.found(),
    });
  };
  return (
    <>
      <CriteriaFields
        editing={editing}
        heading={shared ? t("criteria_and_also", "And also, for this mention: {type}", { type: modelName(props.type) }) : undefined}
        onBack={props.onBack}
        onAfresh={props.onAfresh}
      />
      <CriteriaResult editing={editing} shared={shared} />
      <Show when={similar()}>
        {(found) => <ShareOffer similar={found().found} criteria={found().criteria} except={except} onShared={(made, outcome) => props.onShared?.(made, outcome)} />}
      </Show>
      <div class="flex justify-end gap-2">
        <Show when={shared && props.onStopUsing}>
          <button
            type="button"
            class={[buttonClass("ordinary", "md"), "mr-auto"]}
            title={t("criteria_stop_using_hint", "Cite it no longer: the conditions above are then this mention's criteria")}
            onClick={() => props.onStopUsing?.(editing.criteria())}
          >
            {t("criteria_stop_using", "Stop using")}
          </button>
        </Show>
        <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onCancel()}>
          {t("cancel", "Cancel")}
        </button>
        <button type="button" class={buttonClass("primary", "md")} disabled={!ready()} onClick={done}>
          {t("criteria_done", "Done")}
        </button>
      </div>
    </>
  );
}
