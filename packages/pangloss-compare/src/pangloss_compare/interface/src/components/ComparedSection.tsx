import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import {
  badgeClass,
  buttonClass,
  createInBrowser,
  SectionBar,
  useApi,
  useComponent,
  useModels,
  useModules,
  userIsLoggedIn,
  useSessionKey,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { getComparison } from "../api";
import type { Comparison, EntityChip, PairEntry, Relation, StatementChip } from "../api";
import {
  barWidth,
  byClass,
  comparePath,
  fieldOf,
  fieldsSaid,
  figure,
  HOW_WORDS,
  isCompared,
  itemHref,
  mergeHref,
  nearGroups,
  pairHref,
  RELATION_WORDS,
  shownPairs,
} from "../compared";
import type { NearGroup } from "../compared";

const quiet = "text-sm text-slate-500";
const frame = "shrink-0 text-xs font-semibold text-slate-500 uppercase select-none";

/** A relation in words */
function useRelationWords() {
  const { t } = useTranslations();
  return (relation: Relation) => t(...RELATION_WORDS[relation]);
}

/** A user's name: a link to their page for someone logged in, if a module gives one (as the console names them) */
function UserName(props: { username: string }) {
  const { userHref } = useModules();
  return (
    // (reading who is logged in may wait, so it has a boundary of its own)
    <Loading fallback={<span>{props.username}</span>}>
      <Show when={userIsLoggedIn() && userHref(props.username)} fallback={<span>{props.username}</span>}>
        {(href) => (
          <a href={href()} class="underline-offset-2 hover:text-slate-800 hover:underline">
            {props.username}
          </a>
        )}
      </Show>
    </Loading>
  );
}

/** "According to" and the chip of whose claim a statement is */
function Source(props: { source: EntityChip }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  return (
    <span class="flex items-center gap-2" data-testid="compare-source">
      <span class={frame}>{t("compare_according_to", "according to")}</span>
      <ReferenceChip
        type={props.source.type ?? ""}
        label={props.source.label ?? props.source.id}
        href={itemHref({ type: props.source.type ?? "", id: props.source.id })}
      />
    </span>
  );
}

/**
 * One pair: the relation in words (a link to the two side by side), what it says of the fields, "reported" where it
 * only reports, the other statement as a chip, whose claim it is, whether the two are of one document or source, and
 * the newest judgement of it, by whom. The likelihood is the row's title only
 */
function Row(props: { pair: PairEntry; statement: StatementChip }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const definitions = useModels();
  const { t, language, fieldName } = useTranslations();
  const words = useRelationWords();
  const other = () => props.pair.other;
  // (a disagreement "on Town", what was carried out otherwise "(When: late)"; by each field's label)
  const fields = () => {
    const said = fieldsSaid(props.pair);
    if (said.length === 0) return "";
    const named = said
      .map(({ field, how }) => {
        const found = fieldOf(definitions, [props.pair.common, props.statement.type, other().type], field);
        const name = found ? fieldName(found.model, found.name) : field;
        return how ? t("compare_field_how", "{field}: {how}", { field: name, how: t(...HOW_WORDS[how]) }) : name;
      })
      .join(", ");
    return props.pair.relation === "disagree"
      ? t("compare_fields_on", "on {fields}", { fields: named })
      : t("compare_targets", "({fields})", { fields: named });
  };
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
          <span class={[badgeClass, "self-center bg-amber-50 text-amber-800"]} data-testid="compare-reported">
            {t("compare_reported", "reported")}
          </span>
        </Show>
      </span>
      <span class="min-w-0">
        <ReferenceChip type={other().type} label={other().label ?? other().id} href={itemHref(other())} />
      </span>
      {/* (the rest, in a column of its own that wraps) */}
      <span class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Show when={other().source}>{(source) => <Source source={source()} />}</Show>
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

/** The pairs of the route, the superseded folded behind a button that says how many (in the same grid, so that
 *  their columns are the others') */
function ByRule(props: { answer: Comparison }) {
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  const shown = () => shownPairs(props.answer.pairs);
  return (
    <div data-testid="compare-by-rule">
      <ul class={grid}>
        <Rows pairs={shown().open} statement={props.answer.statement} />
        <Show when={shown().superseded.length > 0}>
          <li class={["col-span-3", { "mt-1": shown().open.length > 0 }]}>
            <button
              type="button"
              class={buttonClass("quiet")}
              aria-expanded={open() ? "true" : "false"}
              data-testid="compare-superseded"
              onClick={() => setOpen(!open())}
            >
              {t("compare_superseded", "{count} more, superseded", { count: String(shown().superseded.length) })}
            </button>
          </li>
          <Show when={open()}>
            <Rows pairs={shown().superseded} statement={props.answer.statement} />
          </Show>
        </Show>
      </ul>
      <Show when={props.answer.more}>
        <p class={[quiet, "mt-3"]}>{t("compare_more", "There are more pairs than are shown here")}</p>
      </Show>
    </div>
  );
}

/** Two entities that may be one: their chips, their score (a bar and the figure, as "Similar" has it), the way to
 *  merging them for someone logged in, and the pairs that would then be one event */
function Group(props: { group: NearGroup; statement: StatementChip }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, language } = useTranslations();
  const chip = (entity: EntityChip) => (
    <ReferenceChip
      type={entity.type ?? ""}
      label={entity.label ?? entity.id}
      href={itemHref({ type: entity.type ?? "", id: entity.id })}
    />
  );
  return (
    <li class="flex flex-col gap-2" data-testid="compare-near-group" data-entity={props.group.entity.id} data-near={props.group.near.id}>
      <div class="flex flex-wrap items-center gap-3">
        {chip(props.group.entity)}
        <span class={frame}>{t("compare_and", "and")}</span>
        {chip(props.group.near)}
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
        <Show when={userIsLoggedIn() && props.group.entity.type}>
          <a class={buttonClass("ordinary")} href={mergeHref({ type: props.group.entity.type!, id: props.group.entity.id }, props.group.near)} data-testid="compare-merge">
            {t("compare_merge", "Compare, or merge")}
          </a>
        </Show>
      </div>
      <ul class={["ml-4 border-l-2 border-slate-300 pl-3", grid]}>
        <Rows pairs={props.group.pairs} statement={props.statement} />
      </ul>
    </li>
  );
}

/** The pairs through near entities, under a heading for each class of the entities; what their state is, as "Similar"
 *  says it. Nothing at all where they are not sought (`none`) */
function ThroughNear(props: { answer: Comparison }) {
  const { t, modelName } = useTranslations();
  const state = () => props.answer.near?.state ?? "none";
  const classes = () => byClass(nearGroups(props.answer.pairs));
  return (
    <Show when={state() !== "none"}>
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

function Compared(props: { type: string; id: string }) {
  const api = useApi();
  const session = useSessionKey();
  const { t } = useTranslations();
  const inBrowser = createInBrowser();
  const path = () => comparePath(props.type, props.id);
  const answer = createMemo(() => {
    session();
    return getComparison(api, path());
  });
  // (asked by itself in the browser once the rest is drawn: its searches cost far more, and the rest does not wait)
  const near = createMemo(() => {
    session();
    return inBrowser() ? getComparison(api, path(), true) : null;
  });
  const empty = () => {
    const shown = shownPairs(answer().pairs);
    return shown.open.length + shown.superseded.length === 0;
  };
  return (
    <section data-testid="compare-section">
      <SectionBar>
        {answer().statement.prescribes ? t("compare_heading_prescribed", "Carried out?") : t("compare_heading", "Compared")}
      </SectionBar>
      <ByRule answer={answer()} />
      {/* (nothing by rule: said so until the pairs through near entities say otherwise) */}
      <Show when={empty()}>
        <Show when={inBrowser()} fallback={<Nothing />}>
          <Errored fallback={<Nothing />}>
            <Loading fallback={<Nothing />}>
              <Show when={nearGroups(near()?.pairs ?? []).length === 0}>
                <Nothing />
              </Show>
            </Loading>
          </Errored>
        </Show>
      </Show>
      <Show when={inBrowser()}>
        <Errored fallback={null}>
          <Loading fallback={null}>
            <Show when={near()}>{(found) => <ThroughNear answer={found()} />}</Show>
          </Loading>
        </Errored>
      </Show>
    </section>
  );
}

/**
 * How the statement of the page stands to the statements it is paired with (`itemSections.Compared`), after its
 * contents, on the page of a statement of a compared class only (what the package tells the interface, `extras.
 * compared`: no other is asked). Headed "Carried out?" where the statement prescribes its contents, else "Compared".
 * The pairs by rule first, strongest first, as the route gives them; those another pair supersedes folded; those of
 * two events or that say nothing of each other not shown. Then, asked by itself in the browser once the rest is drawn,
 * the pairs through near entities, grouped by the two entities that would have to be one.
 *
 * It reads `GET /api/compare/{type}/{id}` itself, directly in a memo, under the boundary `ItemSections` gives every
 * section; read again on login and logout (`useSessionKey`). Nothing here writes: a judgement is made on the page of
 * the two side by side, to which each row's relation links.
 */
export default function ComparedSection(props: ItemSectionProps) {
  return (
    <Show when={isCompared(props.model)}>
      <Compared type={props.type} id={props.id} />
    </Show>
  );
}
