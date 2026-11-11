import { ApiError, buttonClass, tableCellClass, tableClass, tableHeadCellClass, tableHeadRowClass, tableRowClass, useApi, useComponent, useTranslations, whileVisible, createFeedReader, createInBrowser } from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createSignal, createStore, Errored, For, Loading, Show, untrack } from "solid-js";
import { cancelJob, deleteJob, fileUrl, startJob } from "../api";
import type { Job, JobKind, Jobs } from "../api";
import { jobsFeed } from "../feed";
import { defaultOptions, formatSize, isActive, kindIsActive } from "../jobs";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

const button = buttonClass("ordinary");
// (the action in a row of the table)
const rowButton = buttonClass("quiet");

const STATE_WORDS: Record<Job["state"], string> = {
  queued: "Queued",
  running: "Running",
  finished: "Finished",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};

function createJobs() {
  const api = useApi();
  const read = createFeedReader<Jobs>(
    (leaving) => whileVisible((signal) => invoke(jobsFeed, { signal }), leaving),
    api,
  );
  const [view] = createStore<Jobs & { ready: boolean }>(
    async function* () {
      // (one connection, closed when the page is left; a reconnect asks for a new access cookie: `createFeedReader`)
      for await (const jobs of read()) yield { ...jobs, ready: true };
    },
    { kinds: [], jobs: [], ready: false },
    { seedLoadingValue: true },
  );
  return view;
}

function KindForm(props: { kind: JobKind; busy: boolean; onRefused: (reason: string) => void }) {
  const api = useApi();
  const { t } = useTranslations();
  const name = untrack(() => props.kind.name);
  const [options, setOptions] = createSignal(untrack(() => defaultOptions(props.kind)));
  const set = (option: string, value: boolean | string) => setOptions((now) => ({ ...now, [option]: value }));
  return (
    <form
      class="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-[0.5px] border-slate-300 p-3"
      data-testid={`admin-job-form-${name}`}
      onSubmit={(event) => {
        event.preventDefault();
        startJob(api, name, options()).catch((error) => props.onRefused(reasonOf(error)));
      }}
    >
      <h3 class="mr-2 text-sm font-semibold uppercase">{t(`${name}_title`, name)}</h3>
      <For each={props.kind.options}>
        {(option) => (
          <Show
            when={option.type === "choice"}
            fallback={
              <label class="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={options()[option.name] === true}
                  onChange={(event) => set(option.name, event.currentTarget.checked)}
                />
                {t(`${name}_option_${option.name}`, option.name)}
              </label>
            }
          >
            <label class="flex items-center gap-1.5 text-sm">
              {t(`${name}_option_${option.name}`, option.name)}
              <select
                class="rounded-xs border-[0.5px] border-slate-400/70 bg-white px-2 py-1 text-sm"
                value={String(options()[option.name])}
                onChange={(event) => set(option.name, event.currentTarget.value)}
              >
                <For each={option.values ?? []}>
                  {(value) => <option value={value} textContent={t(`${name}_${option.name}_${value}`, value)} />}
                </For>
              </select>
            </label>
          </Show>
        )}
      </For>
      <button type="submit" class={`${button} ml-auto`} disabled={props.busy}>
        {t("admin_job_start", "Start")}
      </button>
    </form>
  );
}

function JobRow(props: { job: Job; onRefused: (reason: string) => void }) {
  const api = useApi();
  const { t, language } = useTranslations();
  const refuse = (error: unknown) => props.onRefused(reasonOf(error));
  const state = () =>
    props.job.cancelling
      ? t("admin_job_cancelling", "Cancelling")
      : t(`admin_job_${props.job.state}`, STATE_WORDS[props.job.state]);
  const when = () => new Date(props.job.createdWhen).toLocaleString(language());
  const counts = () =>
    Object.entries(props.job.counts)
      .map(([key, value]) => `${value.toLocaleString(language())} ${t(`${props.job.kind}_count_${key}`, key)}`)
      .join(", ");
  return (
    <tr class={[tableRowClass, "align-top"]} data-testid="admin-job-row" data-state={props.job.state}>
      <td class={tableCellClass}>{t(`${props.job.kind}_title`, props.job.kind)}</td>
      <td class={tableCellClass}>
        <div class="font-semibold">{state()}</div>
        <Show when={isActive(props.job) && props.job.steps !== null}>
          <div class="text-xs text-slate-600">
            {t("admin_job_step", "{step} of {steps}", {
              step: String(props.job.step),
              steps: String(props.job.steps),
            })}{" "}
            {props.job.current ?? ""}
          </div>
        </Show>
        <div class="text-xs text-slate-600" data-testid="admin-job-counts">
          {counts()}
        </div>
        <Show when={props.job.error}>
          <div class="max-w-md text-xs break-words whitespace-pre-wrap text-red-700">{props.job.error}</div>
        </Show>
      </td>
      <td class={[tableCellClass, "text-slate-600"]}>{props.job.createdBy}</td>
      <td class={[tableCellClass, "whitespace-nowrap text-slate-600"]}>{when()}</td>
      <td class={tableCellClass}>
        <For each={props.job.files}>
          {(file) => (
            <a class="block underline" href={fileUrl(props.job.id, file.name)} download={file.name} target="_self" rel="external">
              {file.name} ({formatSize(file.size)})
            </a>
          )}
        </For>
      </td>
      <td class={[tableCellClass, "text-right"]}>
        <Show
          when={isActive(props.job)}
          fallback={
            <button type="button" class={rowButton} onClick={() => deleteJob(api, props.job.id).catch(refuse)}>
              {t("admin_job_delete", "Delete")}
            </button>
          }
        >
          <button
            type="button"
            class={rowButton}
            disabled={props.job.cancelling}
            onClick={() => cancelJob(api, props.job.id).catch(refuse)}
          >
            {t("admin_job_cancel", "Cancel")}
          </button>
        </Show>
      </td>
    </tr>
  );
}

function JobsContents() {
  const { t } = useTranslations();
  const view = createJobs();
  const [refused, setRefused] = createSignal<string | undefined>();
  return (
    <>
      <Show when={refused()}>
        <p class="mb-3 text-sm text-red-700" role="alert">
          {refused()}
        </p>
      </Show>
      <For each={view.kinds} keyed={(kind) => kind.name}>
        {(kind) => (
          <KindForm kind={kind()} busy={kindIsActive(view.jobs, kind().name)} onRefused={setRefused} />
        )}
      </For>
      <h3 class="mt-6 mb-2 text-xs font-semibold text-slate-500 uppercase">{t("admin_jobs_recent", "Recent jobs")}</h3>
      <Show
        when={view.jobs.length > 0 || !view.ready}
        fallback={<p class="py-4 text-sm text-slate-500">{t("admin_jobs_none", "No jobs yet")}</p>}
      >
        <table class={tableClass}>
          <thead>
            <tr class={tableHeadRowClass}>
              <th class={tableHeadCellClass}>{t("admin_job_kind", "Job")}</th>
              <th class={tableHeadCellClass}>{t("admin_job_state", "State")}</th>
              <th class={tableHeadCellClass}>{t("admin_job_started_by", "Started by")}</th>
              <th class={tableHeadCellClass}>{t("admin_job_when", "When")}</th>
              <th class={tableHeadCellClass}>{t("admin_job_files", "Result")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <For each={view.jobs} keyed={(job) => job.id}>
              {(job) => <JobRow job={job()} onRefused={setRefused} />}
            </For>
          </tbody>
        </table>
      </Show>
    </>
  );
}

export default function JobsSection() {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  // (the feed is opened only in the browser: the server would send a first answer, and the browser would not open it again)
  const inBrowser = createInBrowser();
  const loading = <p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>;
  return (
    <section data-testid="admin-jobs">
      <h2 class="mb-3 text-sm font-semibold uppercase">{t("admin_jobs", "Jobs")}</h2>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Show when={inBrowser()} fallback={loading}>
          <Loading fallback={loading}>
            <JobsContents />
          </Loading>
        </Show>
      </Errored>
    </section>
  );
}
