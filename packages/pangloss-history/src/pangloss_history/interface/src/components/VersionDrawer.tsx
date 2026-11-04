import { useComponent, useTranslations } from "@pangloss/interface-core";
import { Portal } from "@solidjs/web";
import { For, Match, Show, Switch } from "solid-js";
import type { Version, VersionRecord } from "../api";
import { when } from "../format";
import { useProblemLines } from "../problems";
import { OpIcon, useOpWords } from "./OpIcon";

export interface VersionDrawerProps {
  /** Out beside the panel (the panel is open and a version is chosen) */
  open: boolean;
  record?: VersionRecord;
  /** Its content (undefined while it is read) */
  version?: Version;
  error?: unknown;
  /** It is the version the item is at now: nothing to restore */
  current: boolean;
  onRestore: () => void;
  onClose: () => void;
}

/**
 * A version of the item, as the item's page shows the item, in a drawer that slides out to the left of the history
 * panel, from under it; at its foot, "Restore to this point". Always in the page, under the panel and inert while it is
 * closed, so that it slides.
 */
export function VersionDrawer(props: VersionDrawerProps) {
  const ItemContents = useComponent("ItemContents");
  const { t, language } = useTranslations();
  const opWords = useOpWords();
  const problemLines = useProblemLines();
  const shown = () => (props.open ? props.record : undefined);
  return (
    <Portal>
      <section
        aria-label={t("history_version", "Version {version}", { version: String(props.record?.version ?? "") })}
        aria-hidden={props.open ? undefined : "true"}
        inert={!props.open}
        data-testid="history-drawer"
        data-open={props.open ? "true" : "false"}
        data-version={props.record?.version}
        class={[
          // (beside the panel, which is 32rem wide; under it, z-10, so that it comes out from beneath it)
          "fixed top-14 right-[32rem] bottom-0 z-10 flex w-[44rem] max-w-[calc(100vw-35rem)] flex-col rounded-tl-xs border-[0.5px] border-r-0 border-slate-400/70 bg-white text-slate-800 shadow-lg transition-transform duration-300 ease-out",
          { "translate-x-0": props.open, "translate-x-[calc(100%+32rem)]": !props.open },
        ]}
      >
        <header class="flex h-10 shrink-0 items-center justify-between gap-2 border-b-[0.5px] border-slate-400/70 bg-slate-50 pr-1 pl-3 text-xs">
          <Show when={props.record}>
            {(record) => (
              <span class="flex min-w-0 items-center gap-2 text-slate-600">
                <span class="shrink-0 rounded-xs bg-sky-600 px-1.5 py-0.5 text-[0.65rem] font-bold text-white tabular-nums">
                  v{record().version}
                </span>
                <OpIcon op={record().op} class="size-3" />
                <span class="truncate font-semibold uppercase">{opWords(record())}</span>
                <span class="truncate">
                  · {record().who} · {when(record().at, language())}
                </span>
              </span>
            )}
          </Show>
          <button
            type="button"
            class="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-xs hover:bg-slate-400/40"
            aria-label={t("history_close_version", "Close this version")}
            title={t("history_close_version", "Close this version")}
            onClick={() => props.onClose()}
          >
            <svg viewBox="0 0 24 24" class="size-4 fill-none stroke-current stroke-2" stroke-linecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto p-5" data-testid="history-drawer-content">
          <Switch>
            <Match when={props.error}>
              <p class="text-sm text-red-700" role="alert">
                {t("history_version_unreadable", "This version could not be read.")}
              </p>
            </Match>
            <Match when={shown() && props.version}>
              {(version) => (
                <>
                  <Show when={version().upgraded || version().problems.length > 0}>
                    <div class="mb-4 rounded-xs border-[0.5px] border-amber-500/50 bg-amber-50 px-3 py-2 text-xs text-amber-950">
                      <p>
                        <Show
                          when={version().problems.some((problem) => problem.blocking)}
                          fallback={t(
                            "history_upgraded",
                            "This version was saved before some fields were changed. It's shown as it would look today.",
                          )}
                        >
                          <span class="font-semibold">
                            {t("history_cannot_restore", "This version can't be restored as it is.")}
                          </span>{" "}
                          {t("history_cannot_restore_why", "Some things have changed since it was saved:")}
                        </Show>
                      </p>
                      <Show when={version().problems.length > 0}>
                        <ul class="mt-1.5 flex flex-col gap-1 pl-4 list-disc" data-testid="history-problems">
                          <For each={problemLines(version().problems, String(version().content.type ?? ""))}>
                            {(line) => (
                              <li title={line.details.join("\n")} class={{ "text-amber-800": !line.blocking }}>
                                {line.text}
                              </li>
                            )}
                          </For>
                        </ul>
                      </Show>
                    </div>
                  </Show>
                  <h2 class="mb-6 border-b-[0.5px] border-slate-400/70 pb-2 text-xl font-semibold">
                    {(version().content.label as string | undefined) ?? ""}
                  </h2>
                  <ItemContents item={version().content} />
                </>
              )}
            </Match>
            <Match when={shown()}>
              <p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>
            </Match>
          </Switch>
        </div>
        <footer class="flex h-14 shrink-0 items-center justify-between gap-3 border-t-[0.5px] border-slate-400/70 bg-slate-50 px-4">
          <Show
            when={!props.current}
            fallback={
              <span class="text-xs text-slate-500">{t("history_is_current", "This is the version the item is at now.")}</span>
            }
          >
            <span class="text-xs text-slate-500">
              {t("history_restore_hint", "Restoring writes this as a new version: nothing is erased.")}
            </span>
            <button
              type="button"
              class="flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-xs bg-sky-600 px-4 text-xs font-semibold text-white uppercase select-none hover:bg-sky-700 active:bg-sky-800 disabled:cursor-default disabled:opacity-50"
              disabled={!props.version || props.version.problems.some((problem) => problem.blocking)}
              data-testid="history-restore"
              onClick={() => props.onRestore()}
            >
              <OpIcon op="restore" class="size-4" />
              {t("history_restore_to", "Restore to this point")}
            </button>
          </Show>
        </footer>
      </section>
    </Portal>
  );
}
