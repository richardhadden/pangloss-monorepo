import {
  buttonClass,
  PageFrame,
  PageTitle,
  readableTime,
  RequireLogin,
  Spinner,
  useApi,
  useComponent,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import { revalidate, useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, createSignal, Errored, Loading, Match, refresh, Show, Switch } from "solid-js";
import { compareHref, getMerge, stands } from "../api";
import type { HeadRef, MergeRecord, MergeResult, UnmergeResult } from "../api";
import { Comparison } from "./Comparison";
import { MergeSummary } from "./MergeSummary";
import { Notice, Pair, StateBadge } from "./parts";
import { UndoReport, UndoScreen } from "./UndoScreen";

/** Who did what to a merge, and when, a line each */
function Story(props: { record: MergeRecord }) {
  const { t, language } = useTranslations();
  const record = () => props.record;
  const at = (when: string | null | undefined) => readableTime(when, language());
  return (
    <ul class="flex flex-col gap-1 text-sm text-slate-700" data-testid="merge-story">
      <Show when={record().proposedBy}>
        <li>
          {t("merge_story_proposed", "Proposed by {who}, {when}", { who: record().proposedBy!, when: at(record().proposedWhen) })}
          <Show when={record().note}>
            <span data-testid="merge-proposal-note">: “{record().note}”</span>
          </Show>
        </li>
      </Show>
      <Show when={record().by}>
        <li>{t("merge_story_made", "Merged by {who}, {when}", { who: record().by!, when: at(record().when) })}</li>
      </Show>
      <Show when={record().state === "rejected"}>
        <li>
          {t("merge_story_rejected", "Rejected by {who}, {when}", { who: record().rejectedBy ?? "?", when: at(record().rejectedWhen) })}
          <Show when={record().reason}>
            <span data-testid="merge-rejected-reason">: “{record().reason}”</span>
          </Show>
        </li>
      </Show>
      <Show when={record().state === "stale"}>
        <li data-testid="merge-stale-reason">
          {t("merge_story_stale", "No longer current: {reason}", {
            reason: record().reason ?? t("merge_story_stale_unknown", "the entities have changed since"),
          })}
        </li>
      </Show>
      <Show when={record().undoProposedBy && stands(record())}>
        <li>
          {t("merge_story_undo_proposed", "Undoing it proposed by {who}, {when}", {
            who: record().undoProposedBy!,
            when: at(record().undoProposedWhen),
          })}
          <Show when={record().undoNote}>
            <span data-testid="merge-undo-note">: “{record().undoNote}”</span>
          </Show>
        </li>
      </Show>
      <Show when={record().undoRejectedBy && stands(record())}>
        <li>
          {t("merge_story_undo_rejected", "Undoing it rejected by {who}", { who: record().undoRejectedBy! })}
          <Show when={record().undoRejectedReason}>
            <span>: “{record().undoRejectedReason}”</span>
          </Show>
        </li>
      </Show>
      <Show when={record().state === "undone"}>
        <li>{t("merge_story_undone", "Undone by {who}, {when}", { who: record().undoneBy ?? "?", when: at(record().undoneWhen) })}</li>
      </Show>
    </ul>
  );
}

function OneMerge(props: { id: string }) {
  const api = useApi();
  const toasts = useToasts();
  const { t } = useTranslations();
  const record = createMemo(() => getMerge(api, props.id));
  // (what verifying it just did: said in place of the comparison)
  const [made, setMade] = createSignal<MergeResult>();
  // (and what undoing it just did)
  const [undone, setUndone] = createSignal<{ result: UnmergeResult; heads: Record<string, HeadRef> }>();
  const again = () => {
    void revalidate();
    refresh(record);
  };
  const family = () => record().survivorTypeBefore ?? record().survivorType ?? record().absorbedType ?? "";
  return (
    <div class="flex flex-col gap-5" data-testid="merge-page" data-state={record().state}>
      <div class="flex flex-wrap items-center gap-3">
        <StateBadge record={record()} />
        <Pair record={record()} />
      </div>
      <Story record={record()} />
      <Switch>
        <Match when={made()}>{(result) => <MergeSummary result={result()} />}</Match>
        <Match when={undone()}>
          {(done) => <UndoReport result={done().result} done={true} heads={done().heads} />}
        </Match>
        <Match when={record().state === "proposed"}>
          <Comparison
            type={family()}
            survivor={record().survivor}
            absorbed={record().absorbed}
            proposal={record()}
            onMerged={(result) => {
              toasts?.show(t("merge_done", "Merged"), "success");
              setMade(result);
              again();
            }}
            onProposed={() => again()}
            onRejected={() => {
              toasts?.show(t("merge_rejected", "The proposal is rejected"), "success");
              again();
            }}
          />
        </Match>
        <Match when={stands(record())}>
          <UndoScreen
            record={record()}
            onChanged={again}
            onUndone={(result, heads) => {
              setUndone({ result, heads });
              again();
            }}
          />
        </Match>
        <Match when={record().state === "rejected" || record().state === "stale" || record().state === "undone"}>
          <Notice>
            <span>{t("merge_not_standing", "This merge does not stand: the two are separate entities.")}</span>
            <a
              class={buttonClass("ordinary")}
              href={compareHref(family(), record().survivor, record().absorbed)}
              data-testid="merge-compare-again"
            >
              {t("merge_compare_again", "Compare them again")}
            </a>
          </Notice>
        </Match>
      </Switch>
    </div>
  );
}

/**
 * `/merges/:merge`: one merge. A proposal is the comparison again, with what was proposed, to verify or reject; a
 * merge that stands says what undoing it would do, and undoes it; the rest say what became of them
 */
export default function MergePage(props: RouteProps<"/merges/:merge">) {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("merges", "Merges")} />
        <Console type={t("merges", "Merges")} />
        <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
          <a href="/merges" class="hover:underline">
            {t("merges", "Merges")}
          </a>
        </h1>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p class="pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
            <Show when={props.params.merge} keyed>
              {(id) => <OneMerge id={id} />}
            </Show>
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
