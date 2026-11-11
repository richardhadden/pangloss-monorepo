import { firstParam, numberBadgeClass, useApi, useCurrentUser, useTranslations } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import { createMemo, For, Loading, Show } from "solid-js";
import { getTaskCounts, getUsernames } from "../api";
import type { TaskCounts } from "../api";

/** The kinds of task, each a page of its own */
const TABS = [
  { key: "documents", href: "/review", slot: "review_tab_documents", words: "Documents" },
  { key: "reconciliations", href: "/review/reconciliations", slot: "review_tab_reconciliations", words: "Reconciliations" },
  { key: "identifications", href: "/review/identifications", slot: "review_tab_identifications", words: "Identifications" },
] as const;

export type TaskKind = (typeof TABS)[number]["key"];

/**
 * Whose tasks the page shows, from its address (`?assigned=me`, `none`, or a username): what the API's
 * `assigned_to` takes, or undefined for everyone's
 */
export function useAssigned(): () => string | undefined {
  const [search] = useSearchParams();
  return () => firstParam(search.assigned) || undefined;
}

/** How many tasks a tab has: the counts are read once for the three tabs, each of which waits for them */
function Count(props: { kind: TaskKind; counts: () => TaskCounts }) {
  return (
    <span class={[numberBadgeClass, "bg-slate-200 text-slate-700"]} data-testid={`review-count-${props.kind}`}>
      {props.counts()[props.kind]}
    </span>
  );
}

/** Everyone's name, for an admin to choose whose tasks to see */
function OtherUsers(props: { me?: string }) {
  const api = useApi();
  const users = createMemo(() => getUsernames(api));
  return (
    <For each={users().filter((user) => user.kind !== "toolchain" && user.username !== props.me)}>
      {(user) => <option value={user.username} textContent={user.username} />}
    </For>
  );
}

/**
 * The head of the pages of review: a tab for each kind of task (with how many there are), and whose tasks are shown:
 * everyone's, the reader's own, no one's, and for an admin anyone's. The choice is in the address, and kept from tab
 * to tab.
 */
export function ReviewTabs(props: { kind: TaskKind; version?: number }) {
  const { t } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const assigned = useAssigned();
  // (read once: a prop is a getter, and the session is not to be read from a handler)
  const user = createMemo(() => useCurrentUser());
  const query = () => (assigned() ? `?assigned=${encodeURIComponent(assigned()!)}` : "");
  const api = useApi();
  // (one request for the three tabs; read again when the page says its tasks have changed: `version`)
  const counts = createMemo(() => {
    void props.version;
    return getTaskCounts(api, assigned());
  });
  return (
    <div class="mb-4 flex flex-wrap items-center justify-between gap-4" data-testid="review-tabs">
      <nav
        aria-label={t("review_tasks", "Tasks")}
        class="flex overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white text-xs font-semibold uppercase"
      >
        <For each={TABS}>
          {(tab) => (
            <a
              href={`${tab.href}${query()}`}
              aria-current={props.kind === tab.key ? "page" : undefined}
              data-testid={`review-tab-${tab.key}`}
              class="flex items-center gap-2 border-l-[0.5px] border-slate-400/70 px-4 py-2 select-none first:border-l-0 hover:bg-slate-200 aria-[current=page]:bg-slate-700 aria-[current=page]:text-white"
            >
              {t(tab.slot, tab.words)}
              <Loading fallback={null}>
                <Count kind={tab.key} counts={counts} />
              </Loading>
            </a>
          )}
        </For>
      </nav>
      <label class="flex items-center gap-2 text-xs font-semibold text-slate-600 uppercase">
        {t("review_whose", "Tasks of")}
        <select
          class="rounded-xs border-[0.5px] border-slate-400/70 bg-white px-2 py-1.5 text-sm font-normal normal-case"
          data-testid="review-assigned"
          value={firstParam(search.assigned) ?? ""}
          onChange={(event) => setSearch({ assigned: event.currentTarget.value || undefined, page: undefined })}
        >
          <option value="" textContent={t("review_whose_all", "Everyone")} />
          <option value="me" textContent={t("review_whose_mine", "Me")} />
          <option value="none" textContent={t("review_whose_none", "No one")} />
          <Show when={user()?.admin}>
            <Loading fallback={null}>
              <OtherUsers me={user()?.username} />
            </Loading>
          </Show>
        </select>
      </label>
    </div>
  );
}

/** The frame's heading of the pages of review */
export const reviewHeadingClass = "mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold";
