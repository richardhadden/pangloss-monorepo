import {
  ConsoleButton,
  firstParam,
  numberBadgeClass,
  useApi,
  useComponent,
  useCurrentUser,
  useTranslations,
} from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import { createMemo, For, Loading } from "solid-js";
import { ChoiceFilter } from "./filters";
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

/**
 * The head of the pages of review. In the console, a link for each kind of task (with how many there are): they are
 * pages of their own, so they are where the console's links are, and the one shown is marked. On the page, whose
 * tasks are shown: everyone's, the reader's own, no one's, and for an admin anyone's. That choice is in the address,
 * and kept from one kind of task to another.
 */
export function ReviewTabs(props: { kind: TaskKind; version?: number }) {
  const Console = useComponent("Console");
  const { t } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const assigned = useAssigned();
  // (read once: a prop is a getter, and the session is not to be read from a handler)
  const user = createMemo(() => useCurrentUser());
  const query = () => (assigned() ? `?assigned=${encodeURIComponent(assigned()!)}` : "");
  const api = useApi();
  // (one request for the three links; read again when the page says its tasks have changed: `version`)
  const counts = createMemo(() => {
    void props.version;
    return getTaskCounts(api, assigned());
  });
  // (for an admin, everyone else by name: read only for one, and the menu has the rest until they come)
  const others = createMemo(
    (): Promise<string[]> | string[] =>
      user()?.admin
        ? getUsernames(api).then((users) =>
            users.filter((each) => each.kind !== "toolchain" && each.username !== user()?.username).map((each) => each.username),
          )
        : [],
    { loadingValue: [] as string[] },
  );
  return (
    <>
      <Console type={t("review_queue", "Review")}>
        <For each={TABS}>
          {(tab) => (
            <ConsoleButton
              label={t(tab.slot, tab.words)}
              href={`${tab.href}${query()}`}
              current={props.kind === tab.key}
              text
              badge={
                <Loading fallback={null}>
                  <Count kind={tab.key} counts={counts} />
                </Loading>
              }
            />
          )}
        </For>
      </Console>
      <div class="mb-4 flex flex-wrap items-center justify-end gap-4" data-testid="review-whose">
        <ChoiceFilter
          label={t("review_whose", "Tasks of")}
          value={firstParam(search.assigned) ?? ""}
          options={[
            { value: "", label: t("review_whose_all", "Everyone") },
            { value: "me", label: t("review_whose_mine", "Me") },
            { value: "none", label: t("review_whose_none", "No one") },
            ...others().map((name) => ({ value: name, label: name })),
          ]}
          onChoose={(chosen) => setSearch({ assigned: chosen || undefined, page: undefined })}
        />
      </div>
    </>
  );
}

/** The frame's heading of the pages of review */
export const reviewHeadingClass = "mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold";
