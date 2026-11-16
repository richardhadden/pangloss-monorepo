import { createFeedReader, createInBrowser, useApi, useComponent, useTranslations, whileVisible } from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createStore, Errored, Loading, Show } from "solid-js";
import type { MergeList } from "../api";
import { recentMergesFeed } from "../feed";
import { MergeTable } from "./MergeTable";

function Recent() {
  const api = useApi();
  const { t } = useTranslations();
  const read = createFeedReader<MergeList>(
    (leaving) => whileVisible((signal) => invoke(recentMergesFeed, { signal }), leaving),
    api,
  );
  const [view] = createStore<{ results: MergeList["results"]; ready: boolean }>(
    async function* () {
      // (one connection, closed when the page is left: `createFeedReader`)
      for await (const merges of read()) yield { results: merges.results, ready: true };
    },
    { results: [], ready: false },
    { seedLoadingValue: true },
  );
  return (
    <Show
      when={view.results.length > 0}
      fallback={
        <p class="text-sm text-slate-500" data-testid="admin-merges-none">
          {view.ready ? t("admin_merges_none", "No entities have been merged.") : t("loading", "Loading…")}
        </p>
      }
    >
      <MergeTable merges={view.results} />
    </Show>
  );
}

/**
 * The merges made lately, on `/admin` (`slots.admin`), as they are made: a wrong merge of a busy entity is cheaper
 * to undo the sooner it is seen. Each row leads to the merge, where it is undone.
 */
export default function MergesAdminSection() {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  const inBrowser = createInBrowser();
  const loading = <p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>;
  return (
    <section data-testid="admin-merges">
      <div class="mb-3 flex items-baseline gap-4">
        <h2 class="text-sm font-semibold uppercase">{t("admin_merges", "Entities merged lately")}</h2>
        <a class="text-xs font-semibold text-slate-600 uppercase hover:underline" href="/merges?show=all">
          {t("admin_merges_all", "All merges")}
        </a>
      </div>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Show when={inBrowser()} fallback={loading}>
          <Loading fallback={loading}>
            <Recent />
          </Loading>
        </Show>
      </Errored>
    </section>
  );
}
