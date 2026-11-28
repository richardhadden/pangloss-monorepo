import { createMemo, createSignal, createUniqueId, Errored, For, Loading, onSettled, Show } from "solid-js";
import type { JSX } from "@solidjs/web";
import {
  ApiError,
  AssertionMark,
  badgeClass,
  buttonClass,
  createInBrowser,
  SectionBar,
  useApi,
  useComponent,
  useSessionKey,
  userIsLoggedIn,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { getComparison } from "../api";
import type { Comparison, PairEntry, StatementChip } from "../api";
import {
  barWidth,
  byClass,
  comparePath,
  figure,
  isCompared,
  itemHref,
  mergeHref,
  nearGroups,
  pairHref,
  shownPairs,
} from "../compared";
import type { NearGroup } from "../compared";
import { EntityReference, frame, Sources, useFieldsWords, useRelationWords, UserName } from "./parts";

const quiet = "text-sm text-slate-500";

/**
 * One pair: the relation in words (a link to the two side by side), what it says of the fields, "reported" where it
 * only reports, the other statement as a chip, whose claim it is, whether the two are of one document or source, and
 * the newest judgement of it, by whom. The likelihood is the row's title only
 */
function Row(props: { pair: PairEntry; statement: StatementChip }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, language } = useTranslations();
  const words = useRelationWords();
  const fieldsWords = useFieldsWords();
  const other = () => props.pair.other;
  const fields = () => fieldsWords(props.pair, props.statement);
  const newest = () => props.pair.judgements[0];
  return (
    <li
      class="col-span-3 grid grid-cols-subgrid items-center"
      data-testid="compare-row"
      data-relation={props.pair.relation}
      data-other={other().id}
      title={t("compare_likelihood", "Likelihood {value}", { value: figure(props.pair.likelihood, language()) })}
    >
      <span class="flex items-baseline gap-1.5">
        <a
          href={pairHref(props.pair.common ?? props.statement.type, props.statement.id, other().id)}
          class="text-sm font-semibold text-slate-800 underline-offset-2 hover:underline"
          data-testid="compare-relation"
        >
          {words(props.pair.relation)}
        </a>
        <Show when={fields()}>
          <span class="text-sm text-slate-700" data-testid="compare-fields">
            {fields()}
          </span>
        </Show>
        <Show when={props.pair.reported}>
          {/* (the mark the interface gives what is only reported, by its name) */}
          <AssertionMark status="reported" class="self-center" />
        </Show>
      </span>
      <span class="min-w-0">
        <ReferenceChip type={other().type} label={other().label ?? other().id} href={itemHref(other())} />
      </span>
      {/* (the rest, in a column of its own that wraps) */}
      <span class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Sources sources={other().sources} />
        <Show when={props.pair.within}>
          {(within) => (
            <span class="text-xs text-slate-500" data-testid="compare-within" data-within={within()}>
              {within() === "factoid"
                ? t("compare_within_factoid", "within the same document")
                : t("compare_within_source", "within the same source")}
            </span>
          )}
        </Show>
        <Show when={newest()}>
          {(judgement) => (
            <span class="flex items-center gap-1.5 text-xs text-slate-600" data-testid="compare-judged">
              <span
                class={[badgeClass, "bg-slate-200 text-slate-700"]}
                title={t("compare_worked_out", "Worked out: {relation}", {
                  relation: words(props.pair.workedOut.relation),
                })}
              >
                {t("compare_judged", "Judged")}
              </span>
              <Show when={judgement().createdBy.length > 0}>
                <span>
                  {t("compare_judged_by", "by")} <UserName username={judgement().createdBy[0].username} />
                </span>
              </Show>
              <Show when={judgement().changedSinceCited}>
                <span class="text-amber-800" data-testid="compare-changed">
                  {t("compare_changed", "changed since it was judged")}
                </span>
              </Show>
            </span>
          )}
        </Show>
      </span>
    </li>
  );
}

// (a grid: the relations one column, the chips another, the rest a third)
const grid = "grid grid-cols-[max-content_minmax(0,max-content)_auto] items-center justify-start gap-x-3 gap-y-2";

function Rows(props: { pairs: PairEntry[]; statement: StatementChip }) {
  return (
    <For each={props.pairs} keyed={(pair) => pair.other.id}>
      {(pair) => <Row pair={pair()} statement={props.statement} />}
    </For>
  );
}

/**
 * Rows folded behind a button that says how many (`aria-expanded`, and `aria-controls` the element that holds them),
 * in the same grid, so that their columns are the others'
 */
function Folded(props: { pairs: PairEntry[]; statement: StatementChip; label: string; testid: string; gap: boolean }) {
  const [open, setOpen] = createSignal(false);
  const id = createUniqueId();
  return (
    <Show when={props.pairs.length > 0}>
      <li class={["col-span-3", { "mt-1": props.gap }]}>
        <button
          type="button"
          class={buttonClass("quiet")}
          aria-expanded={open() ? "true" : "false"}
          aria-controls={id}
          data-testid={props.testid}
          onClick={() => setOpen(!open())}
        >
          {props.label}
        </button>
      </li>
      <li id={id} class="col-span-3 grid grid-cols-subgrid" hidden={!open()}>
        <Show when={open()}>
          <ul class="col-span-3 grid grid-cols-subgrid gap-y-2">
            <Rows pairs={props.pairs} statement={props.statement} />
          </ul>
        </Show>
      </li>
    </Show>
  );
}

/** The words of a count: the slot for one, or the slot for any other number (a language may say them otherwise) */
function useCounted() {
  const { t } = useTranslations();
  return (count: number, one: [string, string], many: [string, string]) =>
    count === 1 ? t(...one, { count: "1" }) : t(...many, { count: String(count) });
}

/** The open rows, then those another supersedes and those a person judged two events, each folded */
function Listed(props: { pairs: readonly PairEntry[]; statement: StatementChip; class?: string }) {
  const counted = useCounted();
  const shown = () => shownPairs(props.pairs);
  return (
    <ul class={[grid, props.class]}>
      <Rows pairs={shown().open} statement={props.statement} />
      <Folded
        pairs={shown().superseded}
        statement={props.statement}
        gap={shown().open.length > 0}
        testid="compare-superseded"
        label={counted(
          shown().superseded.length,
          ["compare_superseded_one", "{count} more, superseded"],
          ["compare_superseded", "{count} more, superseded"],
        )}
      />
      <Folded
        pairs={shown().twoEvents}
        statement={props.statement}
        gap={shown().open.length + shown().superseded.length > 0}
        testid="compare-two-events"
        label={counted(
          shown().twoEvents.length,
          ["compare_judged_two_one", "{count} judged two events"],
          ["compare_judged_two", "{count} judged two events"],
        )}
      />
    </ul>
  );
}

/** The pairs of the route, with "there are more" where some were cut */
function ByRule(props: { answer: Comparison }) {
  const { t } = useTranslations();
  return (
    <div data-testid="compare-by-rule">
      <Listed pairs={props.answer.pairs} statement={props.answer.statement} />
      <Show when={props.answer.more}>
        <p class={[quiet, "mt-3"]}>{t("compare_more", "There are more pairs than are shown here")}</p>
      </Show>
    </div>
  );
}

/** Two entities that may be one: their chips, their score (a bar and the figure, as "Similar" has it), the way to
 *  merging them for someone logged in, and the pairs that would then be one event */
function Group(props: { group: NearGroup; statement: StatementChip }) {
  return (
    <li class="flex flex-col gap-2" data-testid="compare-near-group" data-entity={props.group.entity.id} data-near={props.group.near.id}>
      <NearHead group={props.group} />
      <Listed pairs={props.group.pairs} statement={props.statement} class="ml-4 border-l-2 border-slate-300 pl-3" />
    </li>
  );
}

/** The two entities of a group as chips, their score, and "Compare, or merge" for someone logged in (also the head of
 *  the page of two side by side, for a pair through them) */
export function NearHead(props: { group: Pick<NearGroup, "entity" | "near" | "score">; children?: JSX.Element }) {
  const { t, language } = useTranslations();
  return (
    <div class="flex flex-wrap items-center gap-3">
      {props.children}
      <EntityReference entity={props.group.entity} />
      <span class={frame}>{t("compare_and", "and")}</span>
      <EntityReference entity={props.group.near} />
      {/* (slate only: a colour here would mean nothing) */}
      <span
        class="block h-1 w-24 bg-slate-200"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={props.group.score}
        aria-label={t("compare_score", "Similarity {value}", { value: figure(props.group.score, language()) })}
      >
        <span class="block h-full bg-slate-500" style={{ width: barWidth(props.group.score) }} />
      </span>
      <span class="text-xs text-slate-500 tabular-nums" aria-hidden="true">
        {figure(props.group.score, language())}
      </span>
      <Show when={userIsLoggedIn() && props.group.entity.type && props.group.near.type}>
        <a
          class={buttonClass("ordinary")}
          href={mergeHref({ type: props.group.entity.type!, id: props.group.entity.id }, props.group.near)}
          data-testid="compare-merge"
        >
          {t("compare_merge", "Compare, or merge")}
        </a>
      </Show>
    </div>
  );
}

/** The pairs through near entities, under a heading for each class of the entities; what their state is, as "Similar"
 *  says it. Nothing at all where there is nothing to show nor to say (`none`; `ok` with none found; `rebuild_due` to
 *  someone not logged in) */
function ThroughNear(props: { answer: Comparison }) {
  const { t, modelName } = useTranslations();
  const state = () => props.answer.near?.state ?? "none";
  const classes = () => byClass(nearGroups(props.answer.pairs));
  const line = () => state() === "pending" || (state() === "rebuild_due" && userIsLoggedIn());
  return (
    <Show when={state() !== "none" && (classes().length > 0 || line())}>
      <div class="mt-6 flex flex-col gap-4" data-testid="compare-near" data-state={state()}>
        <For each={classes()}>
          {(each) => (
            <div class="flex flex-col gap-3">
              <h3 class="text-xs font-semibold text-slate-700 uppercase select-none">
                {t("compare_near_heading", "If these are the same {label}", { label: modelName(each.type) })}
              </h3>
              <ul class="flex flex-col gap-4">
                <For each={each.groups}>{(group) => <Group group={group} statement={props.answer.statement} />}</For>
              </ul>
            </div>
          )}
        </For>
        <Show when={state() === "pending"}>
          <p class={quiet}>{t("compare_near_pending", "Pairs through similar entities are not worked out yet")}</p>
        </Show>
        <Show when={state() === "rebuild_due" && userIsLoggedIn()}>
          <p class={quiet}>
            {t("compare_near_rebuild_due", "The similarity data is due for a rebuild: pairs through similar entities may be missing")}
          </p>
        </Show>
      </div>
    </Show>
  );
}

/** That there is nothing to compare the statement with, as "Similar" says it has found nothing */
function Nothing() {
  const { t } = useTranslations();
  return (
    <p class={quiet} data-testid="compare-none">
      {t("compare_none", "Nothing found to compare it with")}
    </p>
  );
}

/** A comparison, or null where the route has none of this statement (a 404: one inside a space whose statements are
 *  not compared, or no longer there): no section then, and nothing said of it */
export const comparisonOrNone = (found: Promise<Comparison>): Promise<Comparison | null> =>
  found.catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  });

/** Whether any pair is shown (open, folded, or judged two events) */
const anyShown = (pairs: readonly PairEntry[]) => {
  const shown = shownPairs(pairs);
  return shown.open.length + shown.superseded.length + shown.twoEvents.length > 0;
};

function Compared(props: { type: string; id: string }) {
  const api = useApi();
  const session = useSessionKey();
  const { t } = useTranslations();
  const inBrowser = createInBrowser();
  const path = () => comparePath(props.type, props.id);
  const answer = createMemo(() => {
    session();
    return comparisonOrNone(getComparison(api, path()));
  });
  // (asked by itself in the browser once the rest is drawn: its searches cost far more, and the rest does not wait;
  // not at all where the route has no comparison of the statement)
  const near = createMemo(() => {
    session();
    return inBrowser() && answer() ? getComparison(api, path(), true) : null;
  });
  // (whether the pairs through near entities have come, or failed: a mark for whoever waits for them)
  const [nearSettled, setNearSettled] = createSignal(false);
  return (
    <Show when={answer()}>
      {(found) => (
        <section data-testid="compare-section" data-near-settled={nearSettled() ? "true" : "false"}>
          <SectionBar>
            {found().statement.prescribes
              ? t("compare_heading_prescribed", "Carried out?")
              : t("compare_heading", "Compared")}
          </SectionBar>
          <ByRule answer={found()} />
          <Show when={inBrowser()} fallback={<Show when={!anyShown(found().pairs)}><Nothing /></Show>}>
            <Errored
              fallback={
                <>
                  <Settled onSettled={() => setNearSettled(true)} />
                  <Show when={!anyShown(found().pairs)}>
                    <Nothing />
                  </Show>
                </>
              }
            >
              <Loading
                fallback={
                  <Show when={!anyShown(found().pairs)}>
                    <Nothing />
                  </Show>
                }
              >
                <Show when={near()}>
                  {(nearly) => (
                    <>
                      <Settled onSettled={() => setNearSettled(true)} />
                      {/* (nothing by rule: said so until the pairs through near entities say otherwise) */}
                      <Show when={!anyShown(found().pairs) && nearGroups(nearly().pairs).length === 0}>
                        <Nothing />
                      </Show>
                      <ThroughNear answer={nearly()} />
                    </>
                  )}
                </Show>
              </Loading>
            </Errored>
          </Show>
        </section>
      )}
    </Show>
  );
}

/** Says, once drawn, that it was (in `onSettled`, never while rendering; not on the server) */
function Settled(props: { onSettled: () => void }) {
  onSettled(() => {
    props.onSettled();
  });
  return null;
}

/**
 * How the statement of the page stands to the statements it is paired with (`itemSections.Compared`), after its
 * contents, on the page of a statement of a compared class only (what the package tells the interface, `extras.
 * compared`: no other is asked). Headed "Carried out?" where the statement prescribes its contents, else "Compared".
 * The pairs by rule first, strongest first, as the route gives them; those another pair supersedes folded, and those a
 * person judged to be two events; those the maths alone calls two events or that say nothing of each other not shown.
 * Then, asked by itself in the browser once the rest is drawn, the pairs through near entities, grouped by the two
 * entities that would have to be one. A statement the route has no comparison of (a 404: inside a space whose
 * statements are not compared) has no section, and nothing more is asked.
 *
 * It reads `GET /api/compare/{type}/{id}` itself, directly in a memo, under the boundary `ItemSections` gives every
 * section; read again on login and logout (`useSessionKey`). Nothing here writes: a judgement is made on the page of
 * the two side by side, to which each row's relation links. `data-near-settled` says when the pairs through near
 * entities have come (or failed), for a test that waits on them.
 */
export default function ComparedSection(props: ItemSectionProps) {
  return (
    <Show when={isCompared(props.model)}>
      <Compared type={props.type} id={props.id} />
    </Show>
  );
}
