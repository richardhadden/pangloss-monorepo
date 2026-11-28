import {
  align,
  ApiError,
  AssertionMark,
  buttonClass,
  CELL_TONE,
  ChangedValue,
  ConsoleButton,
  createInBrowser,
  DeleteItemDialog,
  getItem,
  getModel,
  inputClass,
  NotFound,
  PageFrame,
  PageTitle,
  readableTime,
  RowValue,
  SectionBar,
  segmentClass,
  segmentedClass,
  serverProblems,
  Spinner,
  useApi,
  useComponent,
  useErrorText,
  useFieldName,
  useModels,
  userIsLoggedIn,
  useSessionKey,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import type { AlignedRow, ModelDefinitions } from "@pangloss/interface-core";
import type { RouteProps } from "@solidjs/router";
import { action, createMemo, createSignal, Errored, For, Loading, Show, untrack } from "solid-js";
import { getComparison, getPair, recordJudgement } from "../api";
import type { Comparison, Judgement, PairEntry, StatementChip, Verdict } from "../api";
import type { JudgementClass, NoVerdict } from "../compared";
import {
  comparePath,
  figure,
  fittingVerdicts,
  HOW_WORDS,
  isCompared,
  itemHref,
  judgedFields,
  judgementClasses,
  placeProblems,
  RELATION_WORDS,
  verdictRelation,
  pairWith,
  SAYS_FIELDS,
  targetsOf,
} from "../compared";
import { comparisonOrNone, NearHead } from "./ComparedSection";
import {
  frame,
  Sources,
  useAnswerFieldName,
  useFieldsWords,
  useRelationWords,
  UserName,
  useVerdictWords,
} from "./parts";

type Data = Record<string, unknown>;

const quiet = "text-sm text-slate-500";

/** What the page knows of the pair: the two statements in the order shown (the prescription first, where one is),
 *  the entry of the comparison (by rule, or through near entities), or none */
interface Pair {
  first: StatementChip;
  second: StatementChip;
  entry: PairEntry | undefined;
}

/**
 * The rows of the two side by side: the fields of their nearest common class (`type`), the parts paired by place where
 * they share no ids; then the fields only one of the two classes has. The label is the head of each column
 */
export function pairRows(definitions: ModelDefinitions, type: string, first: Data, second: Data): {
  shared: AlignedRow[];
  apart: AlignedRow[];
} {
  const shared = align(definitions, type, [first, second], { pair: "place" }).filter((row) => row.key !== ".label");
  const keys = new Set((getModel(definitions, type)?.fields ?? []).map((field) => field.key));
  const apart: AlignedRow[] = [];
  const seen = new Set<string>();
  for (const own of [first.type, second.type]) {
    if (typeof own !== "string" || own === type) continue;
    for (const row of align(definitions, own, [first, second], { pair: "place" })) {
      const top = row.trail[0];
      const key = top?.kind === "field" ? top.field.key : row.field.key;
      if (key === "label" || keys.has(key) || seen.has(row.key)) continue;
      apart.push(row);
    }
    for (const row of apart) seen.add(row.key);
  }
  return { shared, apart };
}

// (the width of the names; the two statements share the rest)
const COLUMNS = "12rem minmax(0,1fr) minmax(0,1fr)";

function Name(props: { row: AlignedRow; last: boolean }) {
  const fieldName = useFieldName();
  return (
    <div
      class={[
        "border-t-[0.5px] border-r-[0.5px] border-r-slate-400/70 border-t-slate-300 bg-slate-50 py-2 pr-2 text-xs font-semibold text-slate-500 uppercase",
        { "border-t-transparent": props.row.kind === "head" && !props.row.first },
        { "border-b-[0.5px] border-b-slate-400/70": props.last },
      ]}
      style={{ "padding-left": `${0.75 + props.row.depth}rem` }}
    >
      <Show when={props.row.kind === "field" || props.row.first}>{fieldName(props.row.model, props.row.field.key)}</Show>
    </div>
  );
}

/** A row: the first statement's value as it is, the second's marked against it, as history's page marks a version */
function Cells(props: { row: AlignedRow; last: boolean }) {
  return (
    <For each={props.row.cells}>
      {(cell, index) => (
        <div
          class={[
            "flex min-w-0 flex-wrap items-start gap-2 border-x-[0.5px] border-t-[0.5px] border-x-slate-400/70 border-t-slate-200 bg-white py-1.5 pr-3",
            CELL_TONE[cell.mark],
            { "rounded-b-xs border-b-[0.5px] border-b-slate-400/70": props.last },
          ]}
          style={{ "padding-left": `${0.75 + props.row.depth}rem` }}
          data-testid="compare-cell"
          data-row={props.row.key}
          data-mark={cell.mark}
        >
          <Show when={index() > 0} fallback={<RowValue row={props.row} value={cell.value} />}>
            <ChangedValue row={props.row} index={index()} />
          </Show>
        </div>
      )}
    </For>
  );
}

/** The head of a column: the statement as a chip, and whose claim it is */
function ColumnHead(props: { statement: StatementChip }) {
  const ReferenceChip = useComponent("ReferenceChip");
  return (
    <div
      class="flex flex-col gap-2 rounded-t-xs border-[0.5px] border-b-0 border-slate-400/70 bg-slate-100 px-3 py-2"
      data-testid="compare-column"
      data-statement={props.statement.id}
    >
      <ReferenceChip
        type={props.statement.type}
        label={props.statement.label ?? props.statement.id}
        href={itemHref(props.statement)}
      />
      <Sources sources={props.statement.sources} />
    </div>
  );
}

/** The two statements side by side, the differences marked */
function SideBySide(props: { type: string; pair: Pair; first: Data; second: Data }) {
  const definitions = useModels();
  const { t } = useTranslations();
  const rows = createMemo(() => pairRows(definitions, props.type, props.first, props.second));
  // (the last row of all closes the columns)
  const last = () => {
    const all = [...rows().shared, ...rows().apart];
    return all[all.length - 1]?.key;
  };
  return (
    <div class="rounded-xs border-[0.5px] border-slate-400/70 bg-slate-50 pb-3" data-testid="compare-side-by-side">
      <div class="grid pr-3" style={{ "grid-template-columns": COLUMNS }} role="table" aria-label={t("compare_side_by_side", "The two side by side")}>
        <div class="border-r-[0.5px] border-slate-400/70" />
        <ColumnHead statement={props.pair.first} />
        <ColumnHead statement={props.pair.second} />
        <For each={rows().shared} fallback={<p class="col-span-full p-4 text-sm text-slate-500">{t("compare_page_empty", "Nothing to show")}</p>}>
          {(row) => (
            <>
              <Name row={row} last={row.key === last()} />
              <Cells row={row} last={row.key === last()} />
            </>
          )}
        </For>
        <Show when={rows().apart.length > 0}>
          <div class={[frame, "col-span-full border-t-[0.5px] border-slate-400/70 px-3 pt-4 pb-2"]}>
            {t("compare_only_one", "Fields of one of the two only")}
          </div>
          <For each={rows().apart}>
            {(row) => (
              <>
                <Name row={row} last={row.key === last()} />
                <Cells row={row} last={row.key === last()} />
              </>
            )}
          </For>
        </Show>
      </div>
    </div>
  );
}

/** What the comparison says of the pair: the relation in the words of the section's rows, the fields or targets,
 *  "reported", one source or document, the likelihood (small: this is the page for detail); for a pair through near
 *  entities, the two that would have to be one. Or that it found no relation */
function Said(props: { pair: Pair; type: string; first: Data; second: Data }) {
  const { t, language, modelName } = useTranslations();
  const definitions = useModels();
  const words = useRelationWords();
  const fieldsWords = useFieldsWords();
  const fieldName = useFieldName();
  const entry = () => props.pair.entry;
  const near = () => entry()?.by.find((reason) => reason.kind === "near" && reason.near && reason.entity.type && reason.near.type);
  // (of a prescription and what came of it, each target, met or missed)
  const targets = () => {
    const found = entry();
    return found ? targetsOf(pairRows(definitions, props.type, props.first, props.second).shared, found) : [];
  };
  // (said above: what the comparison found, or a person's judgement of a pair it did not find)
  const shown = () => {
    const found = entry();
    return found && (foundRelation(found) || found.judged) ? found : undefined;
  };
  return (
    <div class="mb-8 flex flex-col gap-3" data-testid="compare-said">
      <Show when={near()}>
        {(reason) => (
          <NearHead group={{ entity: reason().entity, near: reason().near!, score: reason().score ?? 0 }}>
            <span class={frame} data-testid="compare-if-same">
              {t("compare_if_same", "If these are the same {label}", { label: modelName(reason().entity.type ?? "") })}
            </span>
          </NearHead>
        )}
      </Show>
      <Show
        when={shown()}
        fallback={
          <p class="text-sm text-slate-700" data-testid="compare-no-relation">
            {t("compare_no_relation", "The comparison found no relation between these two.")}
          </p>
        }
      >
        {(found) => (
          <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span class="text-lg font-semibold text-slate-800" data-testid="compare-relation" data-relation={found().relation}>
              {words(found().relation)}
            </span>
            <Show when={fieldsWords(found(), props.pair.first.id === found().other.id ? props.pair.second : props.pair.first)}>
              {(said) => (
                <span class="text-sm text-slate-700" data-testid="compare-fields">
                  {said()}
                </span>
              )}
            </Show>
            <Show when={found().reported}>
              <AssertionMark status="reported" class="self-center" />
            </Show>
            <Show when={found().within}>
              {(within) => (
                <span class="text-xs text-slate-500" data-testid="compare-within" data-within={within()}>
                  {within() === "factoid"
                    ? t("compare_within_factoid", "within the same document")
                    : t("compare_within_source", "within the same source")}
                </span>
              )}
            </Show>
            <span class="text-xs text-slate-500 tabular-nums" data-testid="compare-likelihood">
              {t("compare_likelihood", "Likelihood {value}", { value: figure(found().likelihood, language()) })}
            </span>
            {/* (what the maths said, where a person's judgement says otherwise) */}
            <Show when={found().judged && !foundRelation(found())}>
              <span class="text-xs text-slate-500" data-testid="compare-worked-out">
                {t("compare_worked_out_none", "Worked out: no relation")}
              </span>
            </Show>
            <Show when={found().judged && foundRelation(found()) && found().workedOut.relation !== found().relation}>
              <span class="text-xs text-slate-500" data-testid="compare-worked-out">
                {t("compare_worked_out", "Worked out: {relation}", { relation: words(found().workedOut.relation) })}
              </span>
            </Show>
          </div>
        )}
      </Show>
      <Show when={targets().length > 0}>
        <ul class="flex flex-wrap items-center gap-2" data-testid="compare-targets">
          <For each={targets()}>
            {(target) => (
              <li
                class={[
                  "rounded-xs border-[0.5px] px-2 py-0.5 text-xs",
                  {
                    "border-slate-400/70 text-slate-700": target.how === "met",
                    "border-amber-500 bg-amber-50 text-amber-900": target.how !== "met",
                  },
                ]}
                data-target={target.key}
                data-how={target.how}
              >
                {t("compare_field_how", "{field}: {how}", {
                  field: fieldName(target.model, target.key),
                  how:
                    target.how === "met"
                      ? t("compare_how_met", "met")
                      : target.how === "missed"
                        ? t("compare_how_missed", "missed")
                        : t(...HOW_WORDS[target.how]),
                })}
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

/** Why no judgement is offered, in words */
function NoJudgement(props: { why: NoVerdict | "no_class" }) {
  const { t } = useTranslations();
  return (
    <p class={quiet} data-testid="compare-no-judgement" data-why={props.why}>
      <Show when={props.why === "two_prescriptions"}>
        {t("compare_no_judgement_two_prescriptions", "Two prescriptions are not judged as one event: no judgement is offered.")}
      </Show>
      <Show when={props.why === "says_nothing"}>
        {t("compare_no_judgement_says_nothing", "One of the two says nothing either way of what it holds: no judgement is offered.")}
      </Show>
      <Show when={props.why === "unrelated"}>
        {t("compare_no_judgement_unrelated", "The two are of classes that are not related: no judgement is offered.")}
      </Show>
      <Show when={props.why === "no_class"}>
        {t("compare_no_judgement_class", "The project declares no judgement for these statements.")}
      </Show>
    </p>
  );
}

/**
 * "Your judgement": the verdicts that fit the pair as a choice; for a disagreement or what was done otherwise, which
 * fields (those of the nearest class both are, ticked as the comparison found them); a note; "Record". By the ordinary
 * create of the project's class (the first by name that cites these two: `judgementClasses`), the prescription in
 * `statement`. What the API refuses is said as a refused save is: a red toast, and at the part it is about
 */
function JudgementForm(props: {
  pair: Pair;
  type: string;
  judgementClass: JudgementClass;
  verdicts: readonly Verdict[];
  onRecorded: () => void;
}) {
  const api = useApi();
  const definitions = useModels();
  const toasts = useToasts();
  const errorText = useErrorText();
  const { t, tDefault, fieldName } = useTranslations();
  const verdictWords = useVerdictWords();
  const [verdict, setVerdict] = createSignal<Verdict>();
  // (ticked as the comparison found them: what the maths said, whatever a person said since)
  const found = untrack(() => props.pair.entry?.workedOut.fields ?? []);
  const [fields, setFields] = createSignal<string[]>(found);
  const [note, setNote] = createSignal("");
  const [problems, setProblems] = createSignal<{ at: string; message: string }[]>([]);
  const [sending, setSending] = createSignal(false);
  const shared = () => judgedFields(definitions, props.type);
  const saysFields = () => {
    const chosen = verdict();
    return chosen !== undefined && SAYS_FIELDS.includes(chosen);
  };
  const at = (part: string) => problems().filter((problem) => problem.at === part);

  const send = action(function* (body: Parameters<typeof recordJudgement>[2]) {
    yield recordJudgement(api, props.judgementClass.name, body);
  });

  async function record() {
    const chosen = verdict();
    if (!chosen) return;
    // (the label every reader sees: in the project's default language, not the recorder's)
    const stored = tDefault ?? t;
    const label = stored("compare_judgement_label", "{verdict}: {first} and {second}", {
      verdict: stored(...RELATION_WORDS[verdictRelation(chosen)]),
      first: props.pair.first.label ?? props.pair.first.id,
      second: props.pair.second.label ?? props.pair.second.id,
    });
    // (the prescription in `statement`; two reports as the class cites them)
    const [cited, citing] = props.judgementClass.swapped
      ? [props.pair.second, props.pair.first]
      : [props.pair.first, props.pair.second];
    setProblems([]);
    setSending(true);
    try {
      await send({
        label,
        verdict: chosen,
        fields: saysFields() ? fields() : [],
        note: note(),
        statement: { type: cited.type, id: cited.id },
        other: { type: citing.type, id: citing.id },
      });
    } catch (error) {
      setSending(false);
      if (error instanceof ApiError && error.status === 422) {
        const { placed, unplaced } = placeProblems(serverProblems(definitions, error.detail));
        setProblems(placed);
        toasts?.show(
          [
            placed.length > 0
              ? t("not_saved_problem", "Not saved: a field has a problem, marked in red")
              : t("not_saved", "Not saved"),
            ...unplaced,
          ].join(" · "),
          "error",
        );
      } else {
        toasts?.show(errorText(error), "error");
      }
      return;
    }
    setSending(false);
    setVerdict(undefined);
    setNote("");
    toasts?.show(t("compare_recorded", "Judgement recorded: {verdict}", { verdict: verdictWords(chosen) }));
    props.onRecorded();
  }

  const Problems = (problemsProps: { part: string }) => (
    <Show when={at(problemsProps.part).length > 0}>
      <ul class="mt-0.5 flex flex-col text-xs text-red-700" data-testid="compare-problems" data-part={problemsProps.part}>
        <For each={at(problemsProps.part)}>{(problem) => <li>{problem.message}</li>}</For>
      </ul>
    </Show>
  );

  return (
    <div class="flex flex-col gap-4" data-testid="compare-judge">
      <div class="flex flex-col gap-1">
        <span class={frame}>{t("compare_verdict", "Verdict")}</span>
        <div class={segmentedClass} role="radiogroup" aria-label={t("compare_verdict", "Verdict")}>
          <For each={props.verdicts}>
            {(each) => (
              <button
                type="button"
                role="radio"
                aria-checked={verdict() === each ? "true" : "false"}
                class={segmentClass(verdict() === each)}
                data-verdict={each}
                onClick={() => setVerdict(each)}
              >
                {verdictWords(each)}
              </button>
            )}
          </For>
        </div>
        <Problems part="verdict" />
        <Problems part="statement" />
        <Problems part="other" />
      </div>
      <Show when={saysFields()}>
        <fieldset class="flex flex-col gap-1" data-testid="compare-judge-fields">
          <legend class={frame}>
            {verdict() === "disagree"
              ? t("compare_fields_disagreed", "Disagree on")
              : t("compare_fields_missed", "Targets missed")}
          </legend>
          <div class="flex flex-wrap gap-x-5 gap-y-1 pt-1">
            <For each={shared()}>
              {(field) => (
                <label class="flex items-center gap-1.5 text-sm text-slate-800">
                  <input
                    type="checkbox"
                    class="size-4"
                    value={field.key}
                    checked={fields().includes(field.key)}
                    onChange={(event) => {
                      const on = event.currentTarget.checked;
                      setFields((was) => (on ? [...was.filter((key) => key !== field.key), field.key] : was.filter((key) => key !== field.key)));
                    }}
                  />
                  {fieldName(props.type, field.name)}
                </label>
              )}
            </For>
          </div>
          <Problems part="fields" />
        </fieldset>
      </Show>
      <label class="flex max-w-2xl flex-col gap-1">
        <span class={frame}>{t("compare_note", "Note")}</span>
        <textarea
          class={[inputClass, { "border-red-700": at("note").length > 0 }]}
          rows={3}
          value={note()}
          onInput={(event) => setNote(event.currentTarget.value)}
          data-testid="compare-note"
        />
        <Problems part="note" />
      </label>
      <div>
        <button
          type="button"
          class={buttonClass("primary")}
          disabled={!verdict() || sending()}
          onClick={() => void record()}
          data-testid="compare-record"
        >
          {t("compare_record", "Record")}
        </button>
      </div>
    </div>
  );
}

/** One earlier judgement: its chip (to its own page), the verdict in words, the fields, the note, who and when, the
 *  notice that a statement changed since; Delete for someone logged in (the API's rule: any of them may delete a
 *  document; the dialog asks it first) */
function Earlier(props: { judgement: Judgement; types: readonly (string | null | undefined)[]; onDeleted: () => void }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, language } = useTranslations();
  const verdictWords = useVerdictWords();
  const name = useAnswerFieldName();
  const [asking, setAsking] = createSignal(false);
  const fields = () => props.judgement.fields.map((key) => name(props.types, key)).join(", ");
  return (
    <li class="flex flex-col gap-1.5 border-t-[0.5px] border-slate-300 py-3" data-testid="compare-judgement" data-verdict={props.judgement.verdict}>
      <div class="flex flex-wrap items-center gap-3">
        <ReferenceChip
          type={props.judgement.type}
          label={props.judgement.label ?? verdictWords(props.judgement.verdict)}
          href={itemHref(props.judgement)}
        />
        <span class="text-sm font-semibold text-slate-800" data-testid="compare-judgement-verdict">
          {verdictWords(props.judgement.verdict)}
        </span>
        <Show when={fields()}>
          <span class="text-sm text-slate-700" data-testid="compare-judgement-fields">
            {t("compare_fields_on", "on {fields}", { fields: fields() })}
          </span>
        </Show>
        <span class="text-xs text-slate-500">
          <Show when={props.judgement.createdBy.length > 0}>
            {t("compare_judged_by", "by")} <UserName username={props.judgement.createdBy[0]!.username} />{" "}
          </Show>
          <Show when={props.judgement.createdWhen}>{(when) => <span>{readableTime(when(), language())}</span>}</Show>
        </span>
        <Show when={props.judgement.changedSinceCited}>
          <span class="text-xs text-amber-800" data-testid="compare-changed">
            {t("compare_changed", "changed since it was judged")}
          </span>
        </Show>
        <Show when={userIsLoggedIn()}>
          <button type="button" class={[buttonClass("quiet"), "ml-auto"]} onClick={() => setAsking(true)} data-testid="compare-delete">
            {t("delete", "Delete")}
          </button>
        </Show>
      </div>
      <Show when={props.judgement.note}>
        <p class="max-w-3xl text-sm whitespace-pre-wrap text-slate-700" data-testid="compare-judgement-note">
          {props.judgement.note}
        </p>
      </Show>
      <Show when={asking()}>
        <Loading fallback={null}>
          <DeleteItemDialog
            type={props.judgement.type}
            id={props.judgement.id}
            label={props.judgement.label ?? undefined}
            onDeleted={() => {
              setAsking(false);
              props.onDeleted();
            }}
            onClose={() => setAsking(false)}
          />
        </Loading>
      </Show>
    </li>
  );
}

/** The page once the comparison, the pair and the two statements are read */
function Shown(props: { type: string; pair: Pair; first: Data; second: Data; onChanged: () => void }) {
  const definitions = useModels();
  const { t } = useTranslations();
  const fitting = () => fittingVerdicts(props.pair.first, props.pair.second, props.pair.entry?.common);
  const classes = () =>
    judgementClasses(
      definitions,
      props.pair.first.type,
      props.pair.second.type,
      !props.pair.first.prescribes && !props.pair.second.prescribes,
    );
  const judgements = () => props.pair.entry?.judgements ?? [];
  const types = () => [props.type, props.pair.first.type, props.pair.second.type];
  return (
    <>
      <Said pair={props.pair} type={props.type} first={props.first} second={props.second} />
      <SideBySide type={props.type} pair={props.pair} first={props.first} second={props.second} />
      <Loading fallback={null}>
        <Show when={userIsLoggedIn()}>
          <section data-testid="compare-your-judgement">
            <SectionBar>{t("compare_your_judgement", "Your judgement")}</SectionBar>
            <Show when={"verdicts" in fitting() ? fitting() : undefined} fallback={<NoJudgement why={(fitting() as { why: NoVerdict }).why} />}>
              {(fits) => (
                <Show when={classes()[0]} fallback={<NoJudgement why="no_class" />}>
                  {(judgementClass) => (
                    <JudgementForm
                      pair={props.pair}
                      type={props.type}
                      judgementClass={judgementClass()}
                      verdicts={(fits() as { verdicts: readonly Verdict[] }).verdicts}
                      onRecorded={props.onChanged}
                    />
                  )}
                </Show>
              )}
            </Show>
          </section>
        </Show>
      </Loading>
      <Show when={judgements().length > 0}>
        <section data-testid="compare-judgements">
          <SectionBar>{t("compare_judgements", "Judgements")}</SectionBar>
          <ul class="flex flex-col">
            <For each={judgements()} keyed={(judgement) => judgement.id}>
              {(judgement) => <Earlier judgement={judgement()} types={types()} onDeleted={props.onChanged} />}
            </For>
          </ul>
        </section>
      </Show>
    </>
  );
}

/** The pair of `a` and `b`: the entry of `a`'s comparison by rule, else through near entities, else the one asked for
 *  by itself (`?other=`, which has `b`'s chip and the judgements of the two); the prescription first where one is.
 *  Undefined where `b` is not a statement of a compared class the reader may see */
function pairOf(a: Comparison, near: Comparison | null, asked: Comparison | null, b: string): Pair | undefined {
  const entry = pairWith(a, b) ?? pairWith(near ?? undefined, b) ?? pairWith(asked ?? undefined, b);
  if (!entry) return undefined;
  const firstIsA = entry.first === a.statement.id;
  return firstIsA
    ? { first: a.statement, second: entry.other, entry }
    : { first: entry.other, second: a.statement, entry };
}

/** Whether the comparison found the pair: not one asked for by itself that the maths calls two events or nothing */
export const foundRelation = (entry: PairEntry | undefined) =>
  entry !== undefined && !(entry.found === "asked" && (entry.workedOut.relation === "two" || entry.workedOut.relation === "nothing"));

function Loaded(props: { type: string; a: string; b: string }) {
  const api = useApi();
  const session = useSessionKey();
  const inBrowser = createInBrowser();
  const { t } = useTranslations();
  const Console = useComponent("Console");
  // (each asked again after a judgement is recorded or deleted: only the one the pair's entry came from)
  const [ruleVersion, setRuleVersion] = createSignal(0);
  const [nearVersion, setNearVersion] = createSignal(0);
  const [askedVersion, setAskedVersion] = createSignal(0);
  const path = () => comparePath(props.type, props.a);
  const comparison = createMemo(() => {
    session();
    ruleVersion();
    return comparisonOrNone(getComparison(api, path()));
  });
  // (`b` not among the pairs by rule: the two by themselves, `?other=` (found by neither, or cut); and, in the browser
  // only, the pairs through near entities, whose searches cost far more: one there is preferred once it has come. A
  // failure of those is no failure of the page)
  const missing = () => {
    const found = comparison();
    return found !== null && pairWith(found, props.b) === undefined;
  };
  const asked = createMemo(() => {
    session();
    askedVersion();
    return missing() ? comparisonOrNone(getPair(api, path(), props.b)) : null;
  });
  const near = createMemo(() => {
    session();
    nearVersion();
    return inBrowser() && missing()
      ? getComparison(api, path(), true).catch((): Comparison | null => null)
      : null;
  });
  const pair = () => {
    const found = comparison();
    return found ? pairOf(found, near(), asked(), props.b) : undefined;
  };
  // (each statement by its own class, as the route names it: the nearest class both are may be none. Read again on
  // login and logout, and only when the two change: one the reader may not see is no page)
  const which = createMemo(() => {
    const shown = pair();
    return shown ? JSON.stringify([shown.first.type, shown.first.id, shown.second.type, shown.second.id]) : null;
  });
  const items = createMemo(() => {
    session();
    const key = which();
    if (!key) return null;
    const [firstType, firstId, secondType, secondId] = JSON.parse(key) as string[];
    return Promise.all([
      getItem(api, firstType!, firstId!, { incomingLimit: 0, extras: false }),
      getItem(api, secondType!, secondId!, { incomingLimit: 0, extras: false }),
    ]).catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    });
  });
  const byId = (id: string) => (items()?.find((item) => item.id === id) ?? {}) as Data;
  const changed = () => {
    const found = pair()?.entry?.found;
    if (found === "near") setNearVersion((n) => n + 1);
    else if (found === "asked") setAskedVersion((n) => n + 1);
    else setRuleVersion((n) => n + 1);
  };
  return (
    <Show when={items() ? pair() : undefined} fallback={<NotFound />}>
      {(shown) => (
        <PageFrame>
          <PageTitle action={t("compare_page_title", "Compared")} type={props.type} label={shown().first.label ?? undefined} />
          <Console type={props.type} label={shown().first.label ?? undefined}>
            <ConsoleButton label={t("compare_back", "Back to the statement")} href={itemHref({ type: props.type, id: props.a })}>
              <svg viewBox="0 0 24 24" class="size-5 select-none fill-none stroke-current stroke-[1.5]" stroke-linecap="square" aria-hidden="true">
                <path d="M15 6l-6 6 6 6" />
              </svg>
            </ConsoleButton>
          </Console>
          <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold" data-testid="compare-page">
            {t("compare_page_heading", "Two statements compared")}
          </h1>
          <Shown
            type={props.type}
            pair={shown()}
            first={byId(shown().first.id)}
            second={byId(shown().second.id)}
            onChanged={changed}
          />
        </PageFrame>
      )}
    </Show>
  );
}

/**
 * `/compare/:type/:a/:b` (`pairHref`, the link of each row of "Compared"): two statements side by side on the fields
 * of their nearest common class (`type`), what the comparison says of them above, and, for someone logged in, a
 * judgement recorded; the judgements made of the pair below, newest first. The pair is the entry for `b` of
 * `GET /api/compare/{type}/{a}`, else of `?near=true`; with none, the two are still side by side, and the page says
 * that the comparison found no relation. A class that is not compared, a statement not there or not the reader's to
 * see: the interface's ordinary not-found. (implementation_docs/compare.md, "The page of two side by side")
 */
export default function PairPage(props: RouteProps<"/compare/:type/:a/:b">) {
  const definitions = useModels();
  const ErrorMessage = useComponent("ErrorMessage");
  const known = () => isCompared(getModel(definitions, props.params.type));
  return (
    <Show when={known()} fallback={<NotFound />}>
      <Errored
        fallback={(error) => (
          <Show
            when={error() instanceof ApiError && [404, 422].includes((error() as ApiError).status)}
            fallback={
              <PageFrame>
                <ErrorMessage error={error()} />
              </PageFrame>
            }
          >
            <NotFound />
          </Show>
        )}
      >
        <Loading fallback={<PageFrame><p class="pt-2 text-slate-500"><Spinner class="size-5" /></p></PageFrame>}>
          <Show when={`${props.params.type}/${props.params.a}/${props.params.b}`} keyed>
            {(_pair: string) => <Loaded type={props.params.type!} a={props.params.a!} b={props.params.b!} />}
          </Show>
        </Loading>
      </Errored>
    </Show>
  );
}
