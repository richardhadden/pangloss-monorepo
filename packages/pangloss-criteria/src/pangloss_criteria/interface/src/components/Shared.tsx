// (shared descriptions where a mention is edited or shown: the summary of one cited with the mention's own conditions,
// the list to start from, the offer to make identical criteria one, and the head of the dialog of a mention that cites one)
import {
  ApiError,
  buttonClass,
  CitationChips,
  CitationMarks,
  inputClass,
  numberBadgeClass,
  Pager,
  useApi,
  useComponent,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import { createMemo, createSignal, For, Loading, onCleanup, Show, untrack } from "solid-js";
import { hrefOf, shareCriteria, sharedDescriptions } from "../api";
import type { Criteria, DocumentRef, Shared, SharedListed, ShareResult, Similar } from "../api";
import { describeCriteria, idsOf } from "../describe";
import type { Part } from "../describe";
import { createLabels } from "../labels";
import type { Labels } from "../labels";
import { DESCRIPTION } from "../value";
import { labelClass } from "./parts";
import { CriteriaSummary } from "./CriteriaSummary";

/** How many shared descriptions "Start from" lists at a time */
export const START_PAGE_SIZE = 5;

/** How many of the documents with the same criteria are shown as chips in the offer to share them (the rest counted) */
export const SIMILAR_SHOWN = 3;

/** The address of the page of a shared description */
export const sharedHref = (id: string) => hrefOf({ type: DESCRIPTION, id });

/**
 * A mention that cites a shared description, summed up: the description as a chip (the citation as the core draws
 * it, without its marks, which the card draws under its bar: `citation`; or, where only the description is known, a
 * chip of it: `shared`), then "+" and the mention's own conditions (`parts`, without the class: `createSummary`'s
 * `afterShared`), if it has any: *Maximilian's secretary* + born: 1500
 */
export function SharedSummary(props: {
  citation?: Record<string, unknown> | null;
  shared?: { id: string; label: string } | null;
  parts: Part[];
  labels: Labels | undefined;
  full?: boolean;
}) {
  const ReferenceChip = useComponent("ReferenceChip");
  return (
    <span class="inline-flex min-w-0 items-center gap-1.5" data-testid="criteria-shared-summary">
      {/* (not a flex item: the chips are as wide as they are, not the whole line) */}
      <span class="inline-block shrink-0" data-testid="criteria-shared">
        <Show
          when={props.citation}
          fallback={
            <Show when={props.shared}>
              {(shared) => <ReferenceChip type={DESCRIPTION} label={shared().label} href={sharedHref(shared().id)} />}
            </Show>
          }
        >
          {(citation) => <CitationChips value={citation()} marks={false} />}
        </Show>
      </span>
      <Show when={props.parts.length > 0}>
        <span class="text-slate-500 select-none">+</span>
        <CriteriaSummary parts={props.parts} labels={props.labels} full={props.full} />
      </Show>
    </span>
  );
}

/** Whether a citation has a mark to show (what it cites was changed or removed since) */
export function citationMarked(citation: Record<string, unknown> | null): boolean {
  if (!citation) return false;
  const state = typeof citation.targetState === "string" ? citation.targetState : "there";
  return state === "removed" || (state === "there" && citation.changedSinceCited === true);
}

/**
 * Under the bar of a mention that cites a shared description which has changed (or gone) since: the marks, as a
 * citation has them, and in a form "Seen" (`onSeen`), which takes the mark off when the document is saved
 */
export function SharedMarks(props: { citation: Record<string, unknown>; onSeen?: () => void }) {
  const { t } = useTranslations();
  return (
    <Show when={citationMarked(props.citation)}>
      <div class="flex flex-wrap items-center gap-2" data-testid="criteria-shared-marks">
        <span class="text-xs text-slate-600">{t("criteria_shared_description", "The shared description")}</span>
        <CitationMarks value={props.citation} onSeen={props.onSeen} />
      </div>
    </Show>
  );
}

/** "Used by N mentions", of a shared description */
function MentionCount(props: { count: number }) {
  const { t } = useTranslations();
  return (
    <span class={numberBadgeClass} title={t("criteria_used_by_hint", "How many mentions cite it")} data-testid="criteria-shared-mentions">
      {props.count === 1
        ? t("criteria_used_by_one", "1 mention")
        : t("criteria_used_by", "{count} mentions", { count: String(props.count) })}
    </span>
  );
}

/**
 * "Start from": the shared descriptions of one of `types` (or a class below one), a page at a time, filtered by their
 * label as it is typed (a moment after the last key); each with how many mentions cite it, its criteria, and **Use**
 * (the mention cites it) and **Copy** (its criteria become the mention's own, with no link to it). Nothing while
 * there are none at all
 */
export function StartFrom(props: { types: string[]; onUse: (shared: SharedListed) => void; onCopy: (shared: SharedListed) => void }) {
  const api = useApi();
  const ReferenceChip = useComponent("ReferenceChip");
  const definitions = useModels();
  const words = useTranslations();
  const { t } = words;
  const [q, setQ] = createSignal("");
  const [page, setPage] = createSignal(1);
  const found = createMemo(() => sharedDescriptions(api, props.types, q(), page(), START_PAGE_SIZE));
  const parts = createMemo(() => found().results.map((each) => describeCriteria(each.criteria, words, definitions)));
  // (the entities they name, by their labels: one request for the page)
  const labels = createLabels(() => parts().flatMap(idsOf));
  let waiting: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(waiting));
  const typed = (text: string) => {
    clearTimeout(waiting);
    waiting = setTimeout(() => {
      setQ(text.trim());
      setPage(1);
    }, 250);
  };
  const filterName = () => t("criteria_start_from_filter", "Find a shared description");
  return (
    <Loading fallback={null}>
      <Show when={found().count > 0 || q() !== ""}>
        <section class="flex flex-col gap-2 border-b-[0.5px] border-slate-400/50 pb-4" aria-label={t("criteria_start_from", "Start from")} data-testid="criteria-start-from">
          <span class={labelClass}>{t("criteria_start_from", "Start from")}</span>
          <input
            class={inputClass}
            aria-label={filterName()}
            placeholder={filterName()}
            onInput={(event) => typed(event.currentTarget.value)}
          />
          <Show
            when={found().results.length > 0}
            fallback={
              <p class="text-sm text-slate-500" data-testid="criteria-start-from-none">
                {t("criteria_start_from_none", "No shared description has that in its label.")}
              </p>
            }
          >
            <ul class="flex flex-col gap-2">
              <For each={found().results}>
                {(shared, index) => (
                  <li class="flex min-w-0 items-center gap-2" data-testid="criteria-start-from-row">
                    <span class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2">
                      <ReferenceChip type={DESCRIPTION} label={shared.label} href={sharedHref(shared.id)} />
                      <MentionCount count={shared.mentions} />
                      <CriteriaSummary parts={parts()[index()] ?? []} labels={labels()} />
                    </span>
                    <button
                      type="button"
                      class={buttonClass("quiet", "sm")}
                      title={t("criteria_use_hint", "Cite it: what it says holds here, and a correction of it reaches this mention")}
                      onClick={() => props.onUse(shared)}
                    >
                      {t("criteria_use", "Use")}
                    </button>
                    <button
                      type="button"
                      class={buttonClass("quiet", "sm")}
                      title={t("criteria_copy_hint", "Copy its criteria into this mention, with no link to it")}
                      onClick={() => props.onCopy(shared)}
                    >
                      {t("criteria_copy", "Copy")}
                    </button>
                  </li>
                )}
              </For>
            </ul>
          </Show>
          <Pager page={page()} pages={Math.max(1, Math.ceil(found().count / START_PAGE_SIZE))} onPage={setPage} />
        </section>
      </Show>
    </Loading>
  );
}

/**
 * At the head of the dialog of a mention that cites a shared description: the description as a chip and the summary
 * of its criteria (read only: they are corrected on its own page); what making it did, if it was just made of these
 * criteria (`made`: the documents changed, and those that could not be, each with why)
 */
export function SharedHead(props: { shared: Shared; made?: ShareResult | null }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const definitions = useModels();
  const words = useTranslations();
  const { t } = words;
  const parts = createMemo(() => describeCriteria(props.shared.criteria, words, definitions));
  const labels = createLabels(() => idsOf(parts()));
  return (
    <section class="flex flex-col gap-2 border-b-[0.5px] border-slate-400/50 pb-4" aria-label={t("criteria_shared_description", "The shared description")} data-testid="criteria-shared-head">
      <span class={labelClass}>{t("criteria_shared_description", "The shared description")}</span>
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <ReferenceChip type={DESCRIPTION} label={props.shared.label} href={sharedHref(props.shared.id)} />
        <CriteriaSummary parts={parts()} labels={labels()} full />
      </div>
      <Show when={props.made}>{(made) => <ShareOutcome made={made()} />}</Show>
    </section>
  );
}

/** What making a shared description of criteria did to the documents that had them */
function ShareOutcome(props: { made: ShareResult }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  return (
    <div class="flex flex-col gap-2 text-sm" data-testid="criteria-share-outcome">
      <p class="text-slate-700">
        {props.made.updated === 1
          ? t("criteria_shared_updated_one", "1 other document now cites it.")
          : t("criteria_shared_updated", "{count} other documents now cite it.", { count: String(props.made.updated) })}{" "}
        {t("criteria_shared_this_one", "This one cites it when it is saved.")}
      </p>
      <Show when={props.made.failed.length > 0}>
        <p class="font-semibold text-red-800" role="alert">
          {t("criteria_shared_failed", "Not changed, and still with criteria of their own:")}
        </p>
        <ul class="flex flex-col gap-2" data-testid="criteria-share-failed">
          <For each={props.made.failed}>
            {(failed) => (
              <li class="flex flex-wrap items-center gap-2">
                <ReferenceChip type={failed.head.type} label={failed.head.label ?? failed.head.id} href={hrefOf(failed.head)} />
                <span class="text-xs text-red-800">{failed.detail}</span>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

/** The documents as chips, the first `shown` of them, and how many more */
function Documents(props: { documents: DocumentRef[]; count: number; shown: number }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const more = () => props.count - Math.min(props.shown, props.documents.length);
  return (
    <span class="flex flex-wrap items-center gap-2" data-testid="criteria-similar-documents">
      <For each={props.documents.slice(0, props.shown)}>
        {(document) => <ReferenceChip type={document.type} label={document.label ?? document.id} href={hrefOf(document)} />}
      </For>
      <Show when={more() > 0}>
        <span class="text-xs text-slate-500">{t("criteria_and_more_documents", "and {count} more", { count: String(more()) })}</span>
      </Show>
    </span>
  );
}

/**
 * The offer to make criteria that other documents use too one shared description: "The same criteria are used in N
 * other documents", the first of them, and a button. It asks first, in the dialog, for a label, and says plainly what
 * it does: those documents are changed, each gets a new version, and their mention cites the new description; this
 * one cites it once it is saved. Nothing is done without the confirmation. Then `POST /api/criteria/share`; `onShared`
 * is given the new description and what was done (the dialog cites it from then on). What the server refuses (too
 * many documents) is said here
 */
export function ShareOffer(props: { similar: Similar; criteria: Criteria; except?: string | null; onShared: (shared: Shared, made: ShareResult) => void }) {
  const api = useApi();
  const { t } = useTranslations();
  const [asking, setAsking] = createSignal(false);
  const [label, setLabel] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  const [refused, setRefused] = createSignal<string | null>(null);
  const count = () => props.similar.count;
  const share = () => {
    const name = untrack(label).trim();
    if (name === "" || untrack(busy)) return;
    const criteria = untrack(() => props.criteria);
    setBusy(true);
    setRefused(null);
    shareCriteria(api, name, criteria, untrack(() => props.except ?? null)).then(
      (made) => {
        setBusy(false);
        props.onShared({ id: made.description.id, label: made.description.label ?? name, criteria }, made);
      },
      (error: unknown) => {
        setBusy(false);
        setRefused(error instanceof ApiError ? error.detail : String(error));
      },
    );
  };
  const labelName = () => t("criteria_share_label", "Label of the shared description");
  return (
    <section class="flex flex-col gap-2 rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100/60 p-3 text-sm" data-testid="criteria-similar">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-slate-700" data-testid="criteria-similar-count">
          {count() === 1
            ? t("criteria_similar_one", "The same criteria are used in 1 other document")
            : t("criteria_similar", "The same criteria are used in {count} other documents", { count: String(count()) })}
        </span>
        <Documents documents={props.similar.documents} count={count()} shown={SIMILAR_SHOWN} />
        <Show when={!asking()}>
          <button type="button" class={buttonClass("ordinary", "sm")} onClick={() => setAsking(true)}>
            {t("criteria_share", "Make them one shared description…")}
          </button>
        </Show>
      </div>
      <Show when={asking()}>
        <div class="flex flex-col gap-2 border-t-[0.5px] border-slate-400/50 pt-2" data-testid="criteria-share-confirm">
          <p class="text-slate-800" role="alert">
            {count() === 1
              ? t(
                  "criteria_share_explained_one",
                  "This makes a shared description of these criteria, and changes 1 other document, which may be someone else's: it gets a new version, in which its mention cites the shared description instead of holding the criteria itself. This mention cites it too, once you save this document.",
                )
              : t(
                  "criteria_share_explained",
                  "This makes a shared description of these criteria, and changes {count} other documents, which may be other people's: each gets a new version, in which its mention cites the shared description instead of holding the criteria itself. This mention cites it too, once you save this document.",
                  { count: String(count()) },
                )}
          </p>
          <Documents documents={props.similar.documents} count={count()} shown={props.similar.documents.length} />
          <label class="flex flex-col gap-1">
            <span class={labelClass}>{labelName()}</span>
            <input
              class={inputClass}
              aria-label={labelName()}
              placeholder={t("criteria_share_label_placeholder", "Maximilian's secretary")}
              onInput={(event) => setLabel(event.currentTarget.value)}
            />
          </label>
          <Show when={refused()}>
            {(detail) => (
              <p class="text-red-800" role="alert" data-testid="criteria-share-refused">
                {detail()}
              </p>
            )}
          </Show>
          <div class="flex justify-end gap-2">
            <button type="button" class={buttonClass("ordinary", "sm")} disabled={busy()} onClick={() => setAsking(false)}>
              {t("cancel", "Cancel")}
            </button>
            <button type="button" class={buttonClass("primary", "sm")} disabled={label().trim() === "" || busy()} onClick={share}>
              {count() === 1
                ? t("criteria_share_confirm_one", "Change 1 document and share")
                : t("criteria_share_confirm", "Change {count} documents and share", { count: String(count()) })}
            </button>
          </div>
        </div>
      </Show>
    </section>
  );
}
