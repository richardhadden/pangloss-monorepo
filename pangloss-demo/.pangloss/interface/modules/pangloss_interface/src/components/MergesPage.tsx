import {
  firstParam,
  MenuSelect,
  PageFrame,
  PageTitle,
  Pager,
  RequireLogin,
  Spinner,
  useApi,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, Errored, Loading, Show } from "solid-js";
import { listMerges, MERGE_STATES } from "../api";
import type { MergeState } from "../api";
import { MergeTable } from "./MergeTable";
import { useStateWords } from "./parts";

const PAGE_SIZE = 50;

/** What the list shows: those that wait for someone (`open`), all of them, or those in one state */
export function shownOf(value: string | undefined): "open" | "all" | MergeState {
  if (value === "all") return "all";
  return MERGE_STATES.includes(value as MergeState) ? (value as MergeState) : "open";
}

function Merges() {
  const api = useApi();
  const { t } = useTranslations();
  const words = useStateWords();
  const [search, setSearch] = useSearchParams();
  const shown = () => shownOf(firstParam(search.show));
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  const merges = createMemo(() => {
    const which = shown();
    return listMerges(api, {
      open: which === "open",
      states: which === "open" || which === "all" ? undefined : [which],
      page: page(),
      pageSize: PAGE_SIZE,
    });
  });
  const options = () => [
    { value: "open", label: t("merges_show_open", "Waiting for someone") },
    { value: "all", label: t("merges_show_all", "All") },
    ...MERGE_STATES.map((state) => ({ value: state, label: words(state) })),
  ];
  return (
    <>
      <div class="mb-4 flex items-center gap-3">
        <span class="text-xs font-semibold text-slate-600 uppercase select-none">{t("merges_show", "Show")}</span>
        <MenuSelect
          label={t("merges_show", "Show")}
          look="small"
          class="w-56"
          value={shown()}
          options={options()}
          onChoose={(value) => setSearch({ show: value === "open" ? null : value, page: null }, { replace: true })}
        />
        <span class="text-sm text-slate-600" data-testid="merges-count">
          {merges().count.toLocaleString()}
        </span>
      </div>
      <Show
        when={merges().results.length > 0}
        fallback={
          <p class="text-sm text-slate-500" data-testid="merges-none">
            {shown() === "open"
              ? t("merges_none_open", "No merge waits for anyone.")
              : t("merges_none", "There are none.")}
          </p>
        }
      >
        <MergeTable merges={merges().results} />
        <Pager
          page={merges().page}
          pages={Math.ceil(merges().count / merges().pageSize)}
          onPage={(next) => setSearch({ page: next === 1 ? null : String(next) })}
        />
      </Show>
    </>
  );
}

/** `/merges`: the merges of entities, those that wait for someone first; each row leads to the page of its merge */
export default function MergesPage() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("merges", "Merges")} />
        <Console type={t("merges", "Merges")} />
        <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">{t("merges", "Merges")}</h1>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p class="pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
            <Merges />
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
