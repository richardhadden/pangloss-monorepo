import {
  ApiError,
  badgeClass,
  buttonClass,
  createFeedReader,
  createInBrowser,
  numberBadgeClass,
  problemsOf,
  readableTime,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useApi,
  useComponent,
  useTranslations,
  whileVisible,
} from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createSignal, createStore, Errored, For, Loading, Show } from "solid-js";
import { startRebuild } from "../api";
import type { PartStatus, ProfileStatus, VectorsStatus } from "../api";
import { statusFeed } from "../feed";
import { reasonsOf, stateOf, weightsText } from "../similar";

// (as the users section says a refusal)
const reasonOf = (error: unknown) =>
  error instanceof ApiError ? problemsOf(error).join("; ") : error instanceof Error ? error.message : String(error);

const STATE_TINT = {
  current: "bg-green-100 text-green-800",
  due: "bg-amber-100 text-amber-900",
  unavailable: "bg-slate-200 text-slate-700",
} as const;

/** What a part or profile is, as a badge, and the reasons the API gives, in its words */
function State(props: { status: PartStatus | ProfileStatus }) {
  const { t } = useTranslations();
  const state = () => stateOf(props.status);
  const words = () =>
    ({
      current: t("vectors_current", "Up to date"),
      due: t("vectors_due", "Rebuild due"),
      unavailable: t("vectors_unavailable", "Unavailable"),
    })[state()];
  return (
    <div class="flex flex-col items-start gap-1">
      <span class={[badgeClass, STATE_TINT[state()]]} data-state={state()}>
        {words()}
      </span>
      <For each={reasonsOf(props.status)}>{(reason) => <span class="text-xs text-slate-600">{reason}</span>}</For>
    </div>
  );
}

function Generation(props: { generation: number | null }) {
  const { t } = useTranslations();
  return (
    <Show when={props.generation !== null} fallback={<span class="text-slate-500">{t("vectors_never_built", "Never built")}</span>}>
      <span class={[numberBadgeClass, "bg-slate-200 text-slate-800"]} data-testid="vectors-generation">
        {props.generation}
      </span>
    </Show>
  );
}

function createStatus() {
  const api = useApi();
  const read = createFeedReader<VectorsStatus>(
    (leaving) => whileVisible((signal) => invoke(statusFeed, { signal }), leaving),
    api,
  );
  const [view] = createStore<{ status: VectorsStatus | null }>(
    async function* () {
      // (one connection, closed when the page is left; a reconnect asks for a new access cookie: `createFeedReader`)
      for await (const status of read()) yield { status };
    },
    { status: null },
    { seedLoadingValue: true },
  );
  return view;
}

function VectorsContents() {
  const api = useApi();
  const { t, language } = useTranslations();
  const view = createStatus();
  const [starting, setStarting] = createSignal(false);
  const [refused, setRefused] = createSignal<string | undefined>();
  const rebuilding = () => view.status?.rebuilding ?? null;
  const number = (value: number) => value.toLocaleString(language());
  const rebuild = () => {
    setRefused(undefined);
    setStarting(true);
    startRebuild(api)
      .catch((error) => setRefused(reasonOf(error)))
      .finally(() => setStarting(false));
  };
  return (
    <>
      <Show when={refused()}>
        <p class="mb-3 text-sm text-red-700" role="alert">
          {refused()}
        </p>
      </Show>
      <div class="mb-2 flex items-center justify-end gap-3">
        <Show when={rebuilding()}>
          {(running) => (
            <span class="text-sm text-slate-600" data-testid="vectors-rebuilding">
              {t("vectors_rebuilding", "Rebuilding since {since} (by {by})", {
                since: readableTime(running().since, language()),
                by: running().by,
              })}
            </span>
          )}
        </Show>
        {/* (no dialog: a rebuild writes a new generation beside the one in use, and destroys nothing) */}
        <button
          type="button"
          class={buttonClass("ordinary")}
          disabled={starting() || rebuilding() !== null || view.status === null}
          onClick={rebuild}
        >
          {t("vectors_rebuild", "Rebuild")}
        </button>
      </div>
      <Show when={view.status}>
        {(status) => (
          <>
            <table class={tableClass} data-testid="vectors-parts">
              <thead>
                <tr class={tableHeadRowClass}>
                  <th class={tableHeadCellClass}>{t("vectors_part", "Part")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_generation", "Generation")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_built", "Built")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_count", "Vectors")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_stale", "Stale")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_state", "State")}</th>
                </tr>
              </thead>
              <tbody>
                <For each={status().parts} keyed={(part) => part.part}>
                  {(part) => (
                    <tr class={[tableRowClass, "align-top"]} data-testid="vectors-part-row" data-part={part().part}>
                      <td class={[tableCellClass, "font-semibold"]}>{part().part}</td>
                      <td class={tableCellClass}>
                        <Generation generation={part().generation} />
                      </td>
                      <td class={[tableCellClass, "whitespace-nowrap text-slate-600"]} data-testid="vectors-built">
                        {readableTime(part().builtAt, language())}
                      </td>
                      <td class={[tableCellClass, "tabular-nums"]}>{number(part().count)}</td>
                      <td class={[tableCellClass, "tabular-nums"]}>{number(part().stale)}</td>
                      <td class={tableCellClass}>
                        <State status={part()} />
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <table class={[tableClass, "mt-6"]} data-testid="vectors-profiles">
              <thead>
                <tr class={tableHeadRowClass}>
                  <th class={tableHeadCellClass}>{t("vectors_profile", "Profile")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_weights", "Weights")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_generation", "Generation")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_built", "Built")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_count", "Vectors")}</th>
                  <th class={tableHeadCellClass}>{t("vectors_state", "State")}</th>
                </tr>
              </thead>
              <tbody>
                <For each={status().profiles} keyed={(profile) => profile.profile}>
                  {(profile) => (
                    <tr
                      class={[tableRowClass, "align-top"]}
                      data-testid="vectors-profile-row"
                      data-profile={profile().profile}
                    >
                      <td class={[tableCellClass, "font-semibold"]}>{profile().profile}</td>
                      <td class={[tableCellClass, "text-slate-600"]}>{weightsText(profile().weights, language())}</td>
                      <td class={tableCellClass}>
                        <Generation generation={profile().generation} />
                      </td>
                      <td class={[tableCellClass, "whitespace-nowrap text-slate-600"]}>
                        {readableTime(profile().builtAt, language())}
                      </td>
                      <td class={[tableCellClass, "tabular-nums"]}>{number(profile().count)}</td>
                      <td class={tableCellClass}>
                        <State status={profile()} />
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </>
        )}
      </Show>
    </>
  );
}

/**
 * Similarity, a part of `/admin`: for each part and profile the generation in use, when it was built, how many vectors
 * (of a part, how many stale), and whether a rebuild is due and why; and a Rebuild button, which starts the admin job
 * `vectors_rebuild` of every part. What is shown comes from a live feed of `GET /api/vectors/status`, so it follows a
 * rebuild whoever started it, and the figures change when it ends.
 */
export default function VectorsAdminSection() {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  // (the feed is opened only in the browser: the server would send a first answer, and the browser would not open it again)
  const inBrowser = createInBrowser();
  const loading = <p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>;
  return (
    <section data-testid="admin-vectors">
      <h2 class="mb-3 text-sm font-semibold uppercase">{t("vectors_admin_title", "Similarity")}</h2>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Show when={inBrowser()} fallback={loading}>
          <Loading fallback={loading}>
            <VectorsContents />
          </Loading>
        </Show>
      </Errored>
    </section>
  );
}
