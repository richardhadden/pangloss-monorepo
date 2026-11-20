import {
  buttonClass,
  createFeedReader,
  createInBrowser,
  DefaultReferenceChip,
  getModel,
  headBarClass,
  kindRule,
  kindTint,
  nestedClass,
  plainTint,
  readableTime,
  Spinner,
  typeChipClass,
  useApi,
  useComponent,
  useModels,
  userIsLoggedIn,
  useTranslations,
  whileVisible,
} from "@pangloss/interface-core";
import type { ViewCardProps } from "@pangloss/interface-core";
import type { JSX } from "@solidjs/web";
import { invoke } from "@solidjs/web/server-functions";
import { createMemo, createSignal, createStore, Errored, lazy, Loading, Show, untrack } from "solid-js";
import { SHOWN } from "../api";
import type { Candidate, CandidatesPage, Criteria, Shared } from "../api";
import { candidatesFeed } from "../feed";
import type { Snapshot } from "../poll";
import { isBare, markOf } from "../same";
import { citationOf, criteriaOf, sameCriteria, savedResult, wordingOf } from "../value";
import { CandidateChips, CandidatePages } from "./Candidates";
import { createSummary, CriteriaSummary } from "./CriteriaSummary";
import { BAR_WORD_BUTTON, BrokenNotice } from "./parts";
import { SharedMarks, SharedSummary } from "./Shared";

// (fetched when it is first opened: only someone logged in has the button, and a reader's page has none of its code)
const ResolveDialog = lazy(() => import("./ResolveDialog"));

/** How a description stands, as the card shows it */
interface CardState {
  count: number;
  /** The first candidates, by label */
  candidates: Candidate[];
  tooBroad: boolean;
  /** Its document was written after it was last evaluated: its candidates are being found again */
  pending: boolean;
  evaluatedWhen: string | null;
  /** Why it is no longer evaluated (its criteria no longer fit the models); its candidates are the last found */
  broken: string | null;
  /** The migration that made it so; `null` without one */
  brokenSince: string | null;
  /** Its criteria: its own, or (a place that is the same one as another) those of the place that holds them */
  criteria: Criteria | null;
  /** How many places of its document are the same one (share its mark); `null` while not known */
  places: number | null;
  /**
   * The shared description whose criteria hold too, as the candidates route says it (of a place that is the same one
   * as another, the one that place cites); `null` while not known, or none
   */
  shared: Shared | null;
}

/** How it stands as its document's read gave it (before the feed has said, and on the server) */
function stateOfItem(item: Record<string, unknown>): CardState {
  const saved = savedResult(item);
  const evaluatedWhen = saved?.evaluatedWhen ?? null;
  const broken = saved?.broken ?? null;
  return {
    count: saved?.count ?? 0,
    candidates: saved?.candidates ?? [],
    tooBroad: saved ? saved.count > saved.candidates.length : false,
    pending: evaluatedWhen === null && broken === null,
    evaluatedWhen,
    broken,
    brokenSince: saved?.brokenSince ?? null,
    // (a place that is the same one as another has none of its own: the candidates route says them)
    criteria: criteriaOf(item),
    places: markOf(item) === null ? 1 : null,
    shared: null,
  };
}

/** How it stands as the candidates route says it (what the route does not say, as `before`) */
function stateOfPage(page: CandidatesPage, before: CardState): CardState {
  return {
    count: page.count,
    candidates: page.candidates,
    tooBroad: page.tooBroad,
    pending: page.pending,
    evaluatedWhen: page.evaluatedWhen,
    broken: page.broken,
    brokenSince: page.brokenSince ?? null,
    criteria: page.criteria === undefined ? before.criteria : criteriaOf({ criteria: page.criteria }),
    places: typeof page.places === "number" ? page.places : before.places,
    shared: page.shared === undefined ? before.shared : page.shared,
  };
}

/** All the linked candidates of a description, a page at a time, in a dialog over the page */
function AllCandidates(props: { id: string; onClose: () => void }) {
  const Modal = useComponent("Modal");
  const { t, modelName } = useTranslations();
  return (
    <Modal title={t("criteria_candidates_of", "Candidates: {name}", { name: modelName("MatchesCriteria") })} onClose={props.onClose} size="lg">
      <div class="overflow-y-auto p-4">
        <CandidatePages id={props.id} />
      </div>
    </Modal>
  );
}

/** "This is…", in the head bar of a saved description, for someone logged in: opens the dialog that resolves it */
function ResolveButton(props: { id: string; places: number | null; marked: boolean }) {
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  return (
    <>
      <button
        type="button"
        class={[BAR_WORD_BUTTON, "text-slate-700 hover:bg-slate-400/30"]}
        aria-haspopup="dialog"
        title={t("criteria_this_is_hint", "Say who it is: one of the candidates takes its place")}
        data-testid="criteria-this-is"
        onClick={() => setOpen(true)}
      >
        {t("criteria_this_is", "This is…")}
      </button>
      <Show when={open()}>
        <Loading fallback={null}>
          <ResolveDialog id={props.id} places={props.places} marked={props.marked} onClose={() => setOpen(false)} />
        </Loading>
      </Show>
    </>
  );
}

/** What the card says of a description's candidates, as it stands */
function Result(props: { id?: string; state: CardState }) {
  const { t, language } = useTranslations();
  const [all, setAll] = createSignal(false);
  const more = () => (props.state.tooBroad ? 0 : props.state.count - Math.min(SHOWN, props.state.candidates.length));
  const counted = () =>
    props.state.count === 1
      ? t("criteria_count_one", "1 candidate")
      : t("criteria_count", "{count} candidates", { count: String(props.state.count) });
  return (
    <>
    <Show when={props.state.broken}>
      {(broken) => <BrokenNotice broken={{ reason: broken(), since: props.state.brokenSince }} />}
    </Show>
    {/* (one that is out of date is not evaluated, whatever was written since: what it has are the last found) */}
    <Show
      when={!props.state.pending || props.state.broken !== null}
      fallback={
        <p class="flex items-center gap-2 text-xs text-slate-500" data-testid="criteria-finding">
          <Spinner />
          {t("criteria_finding", "Finding candidates…")}
        </p>
      }
    >
      <Show
        when={!props.state.tooBroad}
        fallback={
          <p class="text-xs text-slate-500" data-testid="criteria-too-broad">
            {t("criteria_too_broad", "Too broad: {count} found", { count: String(props.state.count) })}
          </p>
        }
      >
        <CandidateChips
          candidates={props.state.candidates}
          faded={props.state.broken !== null}
          after={
            <Show when={more() > 0 && props.id}>
              <button type="button" class={buttonClass("quiet")} onClick={() => setAll(true)}>
                {t("criteria_and_more", "and {count} more", { count: String(more()) })}
              </button>
            </Show>
          }
        />
      </Show>
      <p class="text-xs text-slate-500" data-testid="criteria-count">
        {counted()}
        <Show
          when={props.state.broken === null}
          fallback={
            <>
              {" · "}
              <span data-testid="criteria-last-known">{t("criteria_last_known", "the last found: no longer kept up to date")}</span>
            </>
          }
        >
          <Show when={props.state.evaluatedWhen}>
            {(when) => <> · {t("criteria_updated", "updated {when}", { when: readableTime(when(), language()) })}</>}
          </Show>
        </Show>
        <Show when={(props.state.places ?? 1) > 1}>
          {" · "}
          <span data-testid="criteria-places">
            {t("criteria_in_places", "in {count} places of this document", { count: String(props.state.places) })}
          </span>
        </Show>
      </p>
      <Show when={all() && props.id}>
        {(id) => <AllCandidates id={id()} onClose={() => setAll(false)} />}
      </Show>
    </Show>
    </>
  );
}

/**
 * The card as the feed of the description says it stands, until it has its result (in the browser): `children` draws
 * it. (The whole card, not only its result: the bar has what only the feed says, the criteria of a place that is the
 * same one as another and how many places are)
 */
function Following(props: { id: string; initial: CardState; children: (state: CardState) => JSX.Element }) {
  const api = useApi();
  const read = createFeedReader<Snapshot>(
    (leaving) => whileVisible((signal) => invoke(candidatesFeed, { signal }, props.id), leaving),
    api,
  );
  const [state] = createStore<CardState>(
    async function* () {
      // (one connection, closed when the page is left: `createFeedReader`; a description the reader cannot see
      // keeps what the page read)
      let last = untrack(() => props.initial);
      for await (const page of read())
        if (page) {
          last = stateOfPage(page, last);
          yield last;
        }
    },
    untrack(() => props.initial),
    { seedLoadingValue: true },
  );
  return props.children(state);
}

/**
 * A description where its document is read: the summary, the wording, and its candidates as they are found. A place
 * that is the same one as another says so, and has the summary of the criteria of the place that holds them from its
 * feed (in the browser); the count says how many places are the same one
 */
function Embedded(props: { type: string; item: Record<string, unknown> }) {
  const inBrowser = createInBrowser();
  const id = () => (typeof props.item.id === "string" ? props.item.id : undefined);
  const initial = createMemo(() => stateOfItem(props.item));
  const plain = () => <Shown type={props.type} item={props.item} state={initial()} />;
  return (
    <div class="flex w-full min-w-0 scroll-mt-28 flex-col" data-item-id={id()} data-block data-testid="criteria-card">
      {/* (the feed is opened in the browser only: rendered on the server it would have one answer, and the
          browser would not open it again) */}
      <Show when={inBrowser() && id()} fallback={plain()}>
        {(found) => (
          <Errored fallback={plain()}>
            <Loading fallback={plain()}>
              <Following id={found()} initial={initial()}>
                {(state) => <Shown type={props.type} item={props.item} state={state} />}
              </Following>
            </Loading>
          </Errored>
        )}
      </Show>
    </div>
  );
}

/** The card as the description stands: its head bar, the wording, and the result */
function Shown(props: { type: string; item: Record<string, unknown>; state: CardState }) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const model = () => getModel(definitions, props.type);
  const criteria = createMemo(() => props.state.criteria, { equals: sameCriteria });
  // (the shared description it cites: the citation it holds, or (a place that is the same one as another) the one
  // the candidates route says the place that holds the criteria cites)
  const cited = createMemo(() => citationOf(props.item));
  const shared = createMemo(() => props.state.shared, { equals: (a, b) => a?.id === b?.id && a?.label === b?.label });
  const summary = createSummary(criteria, () => cited() !== null || shared() !== null);
  const wording = () => wordingOf(props.item);
  const id = () => (typeof props.item.id === "string" ? props.item.id : undefined);
  const bare = () => isBare(props.item);
  const tint = () => kindTint(model()?.kind, model()?.interfaceMeta?.colour) || plainTint;
  const rule = () => kindRule(model()?.kind, model()?.interfaceMeta?.colour);
  const loggedIn = createMemo(() => userIsLoggedIn());
  return (
    <>
      <div class={[headBarClass, "h-9"]}>
        <span data-type-info={props.type} data-tint class={[typeChipClass, tint(), rule()]}>
          {modelName(props.type)}
        </span>
        <div class="flex min-w-0 flex-1 items-stretch overflow-hidden rounded-r-xs border-[0.5px] border-l-0 border-slate-400/70">
          {/* (what is done to it is first in the bar, after the type, and says what it does) */}
          <Show when={loggedIn() && id()}>
            {(found) => <ResolveButton id={found()} places={props.state.places} marked={markOf(props.item) !== null} />}
          </Show>
          <div class="flex min-w-0 flex-1 items-center overflow-hidden px-2 whitespace-nowrap">
            <Show when={bare()}>
              <span class="mr-2 shrink-0 text-xs font-semibold text-slate-500 uppercase select-none" data-testid="criteria-same-one-mark">
                {t("criteria_same_one_as", "The same one as")}
              </span>
            </Show>
            <Show
              when={cited() || shared()}
              fallback={
                <Show when={criteria()}>
                  <CriteriaSummary parts={summary.parts()} labels={summary.labels()} />
                </Show>
              }
            >
              <SharedSummary citation={cited()} shared={shared()} parts={summary.parts()} labels={summary.labels()} />
            </Show>
          </div>
        </div>
      </div>
      <div class={["ml-2 pt-3", nestedClass, rule()]}>
        <Show when={cited()}>{(citation) => <SharedMarks citation={citation()} />}</Show>
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
        <Result id={id()} state={props.state} />
      </div>
    </>
  );
}

/**
 * A description where a document is listed among what refers to one of its candidates (on the candidate's page): it
 * is there because of the description, and says so ("identified as candidate"), then what the criteria are, the
 * summary cut short. Not the other candidates, and nothing to do to it
 */
function AsCandidate(props: { item: Record<string, unknown> }) {
  const { t } = useTranslations();
  const criteria = createMemo(() => criteriaOf(props.item));
  const cited = createMemo(() => citationOf(props.item));
  const summary = createSummary(criteria, () => cited() !== null);
  const wording = () => wordingOf(props.item);
  return (
    <span class="inline-flex min-w-0 flex-wrap items-center gap-x-2" data-testid="criteria-as-candidate">
      <span class="text-xs font-semibold text-slate-500 uppercase select-none" data-testid="criteria-candidate-mark">
        {t("criteria_identified_as_candidate", "identified as candidate")}
      </span>
      <Show
        when={cited()}
        fallback={
          <Show when={criteria()}>
            <span class="text-slate-400 select-none">·</span>
            <CriteriaSummary parts={summary.parts()} labels={summary.labels()} />
          </Show>
        }
      >
        {(citation) => (
          <>
            <span class="text-slate-400 select-none">·</span>
            <SharedSummary citation={citation()} parts={summary.parts()} labels={summary.labels()} />
          </>
        )}
      </Show>
      {/* (a place that is the same one as another has no criteria of its own: they are in the other place, which is
          listed too. Nothing is asked for here) */}
      <Show when={isBare(props.item)}>
        <span class="text-slate-400 select-none">·</span>
        <span class="text-sm text-slate-700" data-testid="criteria-same-one-as-another">
          {t("criteria_same_one_as_another", "the same one as another description of this document")}
        </span>
        <Show when={wording()}>
          <span class="text-slate-400 select-none">·</span>
          <span class="text-sm text-slate-700" data-testid="criteria-wording">
            {t("criteria_quoted", "“{wording}”", { wording: wording() })}
          </span>
        </Show>
      </Show>
    </span>
  );
}

/**
 * A description (`MatchesCriteria`) on the page of its document: a head bar with its type and the summary of its
 * criteria, then the wording, and its candidates: five chips, then "and N more", which lists all of them; or, when
 * there are more than are linked, only how many. Until the worker has found them ("Finding candidates…") the card
 * follows the description, and shows them when they come. Someone logged in has "This is…" in its bar, which puts one
 * of them in its place. In a list of what refers to a candidate it is the mark and the summary (`AsCandidate`);
 * elsewhere (a reference to one) it is the plain chip.
 */
export default function CriteriaCard(props: ViewCardProps) {
  const { modelName } = useTranslations();
  return (
    <Show
      when={props.context === "embedded" && props.item}
      fallback={<DefaultReferenceChip type={props.type} label={props.label || modelName(props.type)} href={props.href} />}
    >
      {(item) => (
        <Show when={props.incoming} fallback={<Embedded type={props.type} item={item()} />}>
          <AsCandidate item={item()} />
        </Show>
      )}
    </Show>
  );
}
