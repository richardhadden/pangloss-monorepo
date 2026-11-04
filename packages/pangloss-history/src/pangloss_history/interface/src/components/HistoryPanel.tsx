import { useTranslations } from "@pangloss/interface-core";
import type { ModelDefinition } from "@pangloss/interface-core";
import { Portal } from "@solidjs/web";
import { For, Match, Show, Switch } from "solid-js";
import type { FieldChange, Listing, VersionRecord } from "../api";
import { hasContent } from "../api";
import { CHANGE_TAG, when } from "../format";
import { useFieldName } from "../names";
import { timeline } from "../timeline";
import { HistoryIcon, OpIcon, useOpWords } from "./OpIcon";

export interface HistoryPanelProps {
  /** The item's model (the names of its fields) */
  model: ModelDefinition;
  /** The versions; null if nothing is recorded of the item; undefined while they are read */
  listing: Listing | null | undefined;
  /** Why they could not be read */
  error?: unknown;
  open: boolean;
  onClose: () => void;
  /** The version whose content is out beside the panel */
  selected?: number;
  onSelect: (version: number) => void;
  /** The page that shows every version side by side */
  compareHref: string;
}

/** A field that changed, as a small tag: `+2 Statements`, `−1 Places`, `Text` */
function ChangeTag(props: { change: FieldChange; model: ModelDefinition }) {
  const fieldName = useFieldName();
  const name = () => fieldName(props.model, props.change.key);
  const sign = () =>
    props.change.kind === "added" ? `+${props.change.count} ` : props.change.kind === "removed" ? `−${props.change.count} ` : "";
  return (
    <span
      class={[
        "rounded-xs px-1.5 py-0.5 text-[0.6rem] leading-none font-semibold uppercase ring-[0.5px] ring-inset",
        CHANGE_TAG[props.change.kind],
      ]}
      data-testid="history-change"
      data-kind={props.change.kind}
    >
      {sign()}
      {name()}
    </span>
  );
}

/** One version, condensed: its number, what happened, who and when; its label if it is a new one; what changed */
function VersionCard(props: {
  record: VersionRecord;
  current: boolean;
  /** Its label, if it differs from the version before's */
  label?: string | null;
  selected: boolean;
  model: ModelDefinition;
  onSelect: () => void;
}) {
  const { t, language } = useTranslations();
  const opWords = useOpWords();
  const contents = () => (
    <>
      <div class="flex min-w-0 items-center gap-2 text-[0.65rem] text-slate-500">
        <span
          class={[
            "shrink-0 rounded-xs px-1.5 py-0.5 font-bold text-white tabular-nums",
            props.selected ? "bg-sky-600" : "bg-slate-600",
          ]}
        >
          v{props.record.version}
        </span>
        <span class="flex min-w-0 items-center gap-1 truncate" title={opWords(props.record)}>
          <OpIcon op={props.record.op} class="size-3" />
          <span class="truncate font-semibold text-slate-700 uppercase">{opWords(props.record)}</span>
        </span>
        <Show when={props.current}>
          <span
            class="ml-auto shrink-0 rounded-xs bg-green-100 px-1.5 py-0.5 text-[0.6rem] font-bold text-green-800 uppercase"
            data-testid="history-current"
          >
            {t("history_current", "Current")}
          </span>
        </Show>
      </div>
      <div class="mt-1 flex min-w-0 items-baseline gap-1 text-[0.65rem] text-slate-500">
        <span class="truncate font-semibold">{props.record.who}</span>
        <span class="shrink-0">· {when(props.record.at, language())}</span>
      </div>
      <Show when={props.label}>
        <p class="mt-1.5 truncate text-sm text-slate-800" data-testid="history-label">
          {props.label}
        </p>
      </Show>
      <Show when={(props.record.changes ?? []).length > 0}>
        <div class="mt-1.5 flex flex-wrap gap-1">
          <For each={props.record.changes ?? []}>{(change) => <ChangeTag change={change} model={props.model} />}</For>
        </div>
      </Show>
    </>
  );
  return (
    <Show
      when={hasContent(props.record.op)}
      fallback={
        // (a delete or an undelete changes no content: nothing to look at)
        <div class="rounded-xs border-[0.5px] border-dashed border-slate-400/70 px-3 py-2" data-testid="history-version">
          {contents()}
        </div>
      }
    >
      <button
        type="button"
        aria-pressed={props.selected ? "true" : "false"}
        class={[
          "w-full cursor-pointer rounded-xs border-[0.5px] px-3 py-2 text-left transition-colors",
          props.selected
            ? "border-sky-600 bg-sky-50 ring-1 ring-sky-600"
            : "border-slate-400/70 bg-white hover:bg-slate-50",
        ]}
        data-testid="history-version"
        data-version={props.record.version}
        onClick={() => props.onSelect()}
      >
        {contents()}
      </button>
    </Show>
  );
}

/**
 * The history of an item, in a panel that slides out from the right (below the console bar), as review's does: its
 * versions, newest first, each condensed; one clicked slides its content out beside the panel. Always in the page,
 * off to the right and inert while it is closed, so that it slides.
 */
export function HistoryPanel(props: HistoryPanelProps) {
  const { t } = useTranslations();
  const entries = () => (props.listing ? timeline(props.listing) : []);
  // (the label of each version, shown only where it is not the one of the version before)
  const newLabel = (record: VersionRecord) => {
    const versions = props.listing?.versions ?? [];
    const before = versions
      .slice(0, versions.indexOf(record))
      .reverse()
      .find((each) => hasContent(each.op));
    return record.label && (!before || before.label !== record.label) ? record.label : undefined;
  };
  return (
    <Portal>
      <aside
        aria-label={t("history_panel", "History")}
        aria-hidden={props.open ? undefined : "true"}
        inert={!props.open}
        data-testid="history-panel"
        data-open={props.open ? "true" : "false"}
        class={[
          "fixed top-14 right-0 bottom-0 z-20 flex w-96 max-w-full flex-col rounded-tl-xs border-[0.5px] border-r-0 border-slate-400/70 bg-slate-100/95 text-slate-800 shadow-lg backdrop-blur-md transition-transform duration-200",
          { "translate-x-0": props.open, "translate-x-full": !props.open },
        ]}
      >
        <header class="flex h-10 shrink-0 items-center justify-between border-b-[0.5px] border-slate-400/70 pr-1 pl-3 text-xs font-semibold text-slate-700 uppercase">
          <span class="flex items-center gap-2">
            <HistoryIcon class="size-4" />
            {t("history_panel", "History")}
          </span>
          <span class="flex items-center">
            <Show when={props.listing}>
              <a
                href={props.compareHref}
                class="flex h-8 items-center gap-1.5 rounded-xs px-2 hover:bg-slate-400/40"
                data-testid="history-compare"
              >
                {/* (columns side by side) */}
                <svg
                  viewBox="0 0 24 24"
                  class="size-4 fill-none stroke-current stroke-2"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <path d="M3 4h7v16H3zM14 4h7v16h-7z" />
                </svg>
                {t("history_compare_all", "Compare all")}
              </a>
            </Show>
            <button
              type="button"
              class="flex size-8 cursor-pointer items-center justify-center rounded-xs hover:bg-slate-400/40"
              aria-label={t("history_close", "Close the history")}
              title={t("history_close", "Close the history")}
              onClick={() => props.onClose()}
            >
              <svg
                viewBox="0 0 24 24"
                class="size-4 select-none fill-none stroke-current stroke-2"
                stroke-linecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </span>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <Switch>
            <Match when={props.error}>
              <p class="text-sm text-red-700" role="alert">
                {t("history_unreadable", "The history could not be read.")}
              </p>
            </Match>
            <Match when={props.listing === undefined}>
              <p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>
            </Match>
            <Match when={props.listing === null}>
              <div class="my-6 text-center text-sm text-slate-600" data-testid="history-none">
                <p>{t("history_none", "No versions of this are recorded.")}</p>
                <p class="mt-2 text-xs text-slate-500">
                  {t(
                    "history_none_why",
                    "History began after it was last saved: its next save will be the first version. `pangloss history baseline` records what it is now.",
                  )}
                </p>
              </div>
            </Match>
            <Match when={props.listing}>
              <ol class="flex flex-col gap-2" aria-label={t("history_versions", "Versions")}>
                <For each={entries()}>
                  {(entry) => (
                    <li>
                      <Show
                        when={entry.kind === "version" ? entry : undefined}
                        fallback={
                          <p
                            class="rounded-xs border-[0.5px] border-dashed border-slate-400 px-3 py-1.5 text-center text-[0.65rem] text-slate-500 italic"
                            data-testid="history-gap"
                          >
                            {entry.kind === "gap" && entry.from === entry.to
                              ? t("history_gap_one", "Version {version} was not recorded", { version: String(entry.from) })
                              : t("history_gap", "Versions {from}–{to} were not recorded", {
                                  from: String(entry.kind === "gap" ? entry.from : ""),
                                  to: String(entry.kind === "gap" ? entry.to : ""),
                                })}
                          </p>
                        }
                      >
                        {(version) => (
                          <VersionCard
                            record={version().record}
                            current={version().current}
                            label={newLabel(version().record)}
                            selected={props.selected === version().record.version && hasContent(version().record.op)}
                            model={props.model}
                            onSelect={() => props.onSelect(version().record.version)}
                          />
                        )}
                      </Show>
                    </li>
                  )}
                </For>
              </ol>
            </Match>
          </Switch>
        </div>
      </aside>
    </Portal>
  );
}
