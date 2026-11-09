import {
  ApiError,
  ConsoleButton,
  getItem,
  RequireLogin,
  useApi,
  useComponent,
  useModels,
  useNavExpanded,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, For, Loading, onSettled, Show } from "solid-js";
import { align } from "../align";
import type { AlignedRow } from "../align";
import { getContents } from "../api";
import type { Content, Contents, VersionRecord } from "../api";
import { when } from "../format";
import { useFieldName } from "../names";
import { CELL_TONE, ChangedValue } from "./AlignedCell";
import { OpIcon, useOpWords } from "./OpIcon";

/** A column of the page: a recorded version, or the item as it is now when that was not recorded */
interface Column {
  record?: VersionRecord;
  /** The version the graph has (for a column of what it is now) */
  version: number;
  content: Content;
  current: boolean;
}

/** The columns, oldest first: each recorded version with content, and what the item is now if it is not one of them */
export function columnsOf(contents: Contents, now?: Content): Column[] {
  const columns: Column[] = contents.versions.map((version) => ({
    record: version,
    version: version.version,
    content: version.content,
    current: false,
  }));
  const last = columns[columns.length - 1];
  if (contents.currentVersion !== null && last && last.version === contents.currentVersion) last.current = true;
  else if (contents.currentVersion !== null && now) {
    columns.push({ version: contents.currentVersion, content: now, current: true });
  }
  return columns;
}

// (the width of the names, and of a version)
const NAMES = "14rem";
const COLUMN = "26rem";

function Header(props: { column: Column }) {
  const { t, language } = useTranslations();
  const opWords = useOpWords();
  return (
    <div
      class="sticky top-0 z-10 flex flex-col gap-0.5 rounded-t-xs border-[0.5px] border-b-0 border-slate-400/70 bg-slate-100 px-3 py-2 text-[0.65rem] text-slate-500"
      data-testid="history-column"
      data-version={props.column.version}
    >
      <div class="flex items-center gap-2">
        <span
          class={[
            "rounded-xs px-1.5 py-0.5 font-bold text-white tabular-nums",
            props.column.current ? "bg-green-700" : "bg-slate-600",
          ]}
        >
          v{props.column.version}
        </span>
        <Show
          when={props.column.record}
          fallback={<span class="font-semibold text-slate-700 uppercase">{t("history_not_recorded", "Not recorded")}</span>}
        >
          {(record) => (
            <span class="flex min-w-0 items-center gap-1 truncate font-semibold text-slate-700 uppercase">
              <OpIcon op={record().op} class="size-3" />
              {opWords(record())}
            </span>
          )}
        </Show>
        <Show when={props.column.current}>
          <span class="ml-auto rounded-xs bg-green-100 px-1.5 py-0.5 text-[0.6rem] font-bold text-green-800 uppercase">
            {t("history_current", "Current")}
          </span>
        </Show>
      </div>
      <Show when={props.column.record}>
        {(record) => (
          <span class="truncate">
            <span class="font-semibold">{record().who}</span> · {when(record().at, language())}
          </span>
        )}
      </Show>
    </div>
  );
}

/** The name of a row, in the column of names: its field's (a part only says it as the first of its field) */
function Name(props: { row: AlignedRow; last: boolean }) {
  const fieldName = useFieldName();
  return (
    <div
      class={[
        // (over the versions as they scroll under it: a hairline and a shadow at its right)
        "sticky left-0 z-[5] border-t-[0.5px] border-r-[0.5px] border-r-slate-400/70 border-t-slate-300 bg-slate-50 py-2 pr-2 text-xs font-semibold text-slate-500 uppercase shadow-[6px_0_8px_-6px_rgb(15_23_42/0.25)]",
        { "border-t-transparent": props.row.kind === "head" && !props.row.first },
      ]}
      style={{ "padding-left": `${0.75 + props.row.depth}rem` }}
    >
      <Show when={props.row.kind === "field" || props.row.first}>{fieldName(props.row.model, props.row.field.key)}</Show>
    </div>
  );
}

function Cells(props: { row: AlignedRow; last: boolean }) {
  return (
    <For each={props.row.cells}>
      {(cell, index) => (
        <div
          class={[
            "flex min-w-0 flex-wrap items-start gap-2 border-x-[0.5px] border-t-[0.5px] border-x-slate-400/70 border-t-slate-200 bg-white py-1.5 pr-3",
            CELL_TONE[cell.mark],
            { "rounded-b-xs border-b-[0.5px] border-b-slate-400/70": props.last },
          ]}
          style={{ "padding-left": `${0.75 + props.row.depth}rem` }}
          data-testid="history-cell"
          data-row={props.row.key}
          data-mark={cell.mark}
        >
          <ChangedValue row={props.row} index={index()} />
        </div>
      )}
    </For>
  );
}

/** Every version side by side, in a box that scrolls sideways, starting at the right (the newest) */
export function Compare(props: { type: string; contents: Contents; now?: Content }) {
  const definitions = useModels();
  const { t } = useTranslations();
  const columns = createMemo(() => columnsOf(props.contents, props.now));
  const rows = createMemo(() =>
    align(
      definitions,
      props.type,
      columns().map((column) => column.content),
    ),
  );
  let box: HTMLDivElement | undefined;
  // (the newest is what is looked at first)
  onSettled(() => {
    if (box) box.scrollLeft = box.scrollWidth;
  });
  return (
    <div
      ref={box}
      class="max-h-[calc(100vh-8rem)] overflow-auto rounded-xs border-[0.5px] border-slate-400/70 bg-slate-50 pb-3"
      data-testid="history-compare-box"
    >
      <div
        class="grid gap-x-3 pr-3"
        style={{ "grid-template-columns": `${NAMES} repeat(${columns().length}, ${COLUMN})` }}
        role="table"
        aria-label={t("history_compare", "Every version")}
      >
        <div class="sticky top-0 left-0 z-20 border-r-[0.5px] border-slate-400/70 bg-slate-50 shadow-[6px_0_8px_-6px_rgb(15_23_42/0.25)]" />
        <For each={columns()}>{(column) => <Header column={column} />}</For>
        <For each={rows()} fallback={<p class="col-span-full p-4 text-sm text-slate-500">{t("history_empty", "Nothing to show")}</p>}>
          {(row, index) => (
            <>
              <Name row={row} last={index() === rows().length - 1} />
              <Cells row={row} last={index() === rows().length - 1} />
            </>
          )}
        </For>
      </div>
    </div>
  );
}

function Loaded(props: { type: string; id: string }) {
  const api = useApi();
  const { t } = useTranslations();
  const contents = createMemo(() => getContents(api, props.type, props.id));
  // (what the item is now: its label, and its content if the graph is ahead of the history; none if it is deleted)
  const item = createMemo(() =>
    getItem(api, props.type, props.id).catch((error) => {
      if (error instanceof ApiError && error.status === 404) return undefined;
      throw error;
    }),
  );
  const Console = useComponent("Console");
  return (
    <>
      <Console type={props.type} label={(item()?.label as string | undefined) ?? undefined}>
        <ConsoleButton label={t("history_back", "Back to the item")} href={`/${props.type}/${encodeURIComponent(props.id)}`}>
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-none stroke-current stroke-[1.5]"
            stroke-linecap="square"
            aria-hidden="true"
          >
            <path d="M15 6l-6 6 6 6" />
          </svg>
        </ConsoleButton>
      </Console>
      <h1 class="mb-4 text-xl font-semibold">
        {t("history_page_title", "History of {label}", { label: (item()?.label as string | undefined) ?? props.id })}
      </h1>
      <Compare type={props.type} contents={contents()} now={item() as Content | undefined} />
    </>
  );
}

/** /<type>/<id>/history: every version of an item, side by side, what changed in each marked */
export default function HistoryPage(props: RouteProps<"/:type/:id/history">) {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  const { navPinned } = useNavExpanded();
  const navigate = useNavigate();
  return (
    // (giving up logging in goes back to the item)
    <RequireLogin onCancel={() => navigate(`/${props.params.type}/${encodeURIComponent(props.params.id)}`, { replace: true })}>
      <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>
        <Errored
          fallback={(error) => (
            <Show
              when={error() instanceof ApiError && (error() as ApiError).status === 404}
              fallback={<ErrorMessage error={error()} />}
            >
              <p role="alert">{t("history_none", "No versions of this are recorded.")}</p>
            </Show>
          )}
        >
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <Show when={props.params.id} keyed>
              {(id) => <Loaded type={props.params.type} id={id} />}
            </Show>
          </Loading>
        </Errored>
      </main>
    </RequireLogin>
  );
}
