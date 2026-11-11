import {
  ApiError,
  ConsoleButton,
  useApi,
  useSidePanel,
  useToasts,
  useTranslations,
  userIsLoggedIn,
} from "@pangloss/interface-core";
import type { ConsoleActionProps, ModelDefinition } from "@pangloss/interface-core";
import { revalidate } from "@solidjs/router";
import { createSignal, onSettled, Show, untrack } from "solid-js";
import { getHistory, getVersion, hasContent, restoreVersion } from "../api";
import type { Listing, Version } from "../api";
import { latestContent, undone } from "../timeline";
import { HistoryPanel } from "./HistoryPanel";
import { HistoryIcon } from "./OpIcon";
import { RestoreDialog } from "./RestoreDialog";
import type { Now } from "./RestoreDialog";
import { VersionDrawer } from "./VersionDrawer";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

/** The button, the panel, the drawer of a version and the dialog of a restore, of one item */
function History(props: { type: string; id: string; model: ModelDefinition }) {
  const api = useApi();
  const toasts = useToasts();
  const { t } = useTranslations();
  const type = untrack(() => props.type);
  const id = untrack(() => props.id);
  // (one panel on the right at a time: opening this closes review's, and the other way round)
  const { open, setOpen } = useSidePanel("history");
  // (undefined while it is read; null if nothing is recorded)
  const [listing, setListing] = createSignal<Listing | null | undefined>();
  const [failed, setFailed] = createSignal<unknown>();
  const [selected, setSelected] = createSignal<number>();
  // (the versions read so far, by number, and those that could not be)
  const [versions, setVersions] = createSignal<Record<number, Version>>({});
  const [unreadable, setUnreadable] = createSignal<Record<number, unknown>>({});
  const [confirming, setConfirming] = createSignal(false);
  const [busy, setBusy] = createSignal(false);

  // (`until`: a version that has just been written, which is recorded a moment after the write: asked again, a few
  // times, until it is there)
  const load = (until?: number, tries = 10): Promise<void> => {
    setFailed(undefined);
    return getHistory(api, type, id)
      .then((found) => {
        const recorded = found.versions.some((each) => each.version >= (until ?? 0));
        if (!recorded && tries > 0) {
          return new Promise<void>((resolve) => setTimeout(resolve, 200)).then(() => load(until, tries - 1));
        }
        setListing(found);
      })
      .catch((error) => {
        if (error instanceof ApiError && error.status === 404) setListing(null);
        else {
          console.error(error);
          setFailed(error);
        }
      });
  };
  const want = (version: number) => {
    if (untrack(versions)[version] || untrack(unreadable)[version]) return;
    getVersion(api, type, id, version)
      .then((found) => setVersions((was) => ({ ...was, [version]: found })))
      .catch((error) => setUnreadable((was) => ({ ...was, [version]: error })));
  };

  const record = () => {
    const version = selected();
    return version === undefined
      ? undefined
      : listing()?.versions.findLast((each) => each.version === version && hasContent(each.op));
  };
  const latest = () => {
    const found = listing();
    return found ? latestContent(found) : undefined;
  };
  // (the graph is at a version that was not recorded: what changed in it cannot be shown)
  const unrecorded = () => {
    const found = listing();
    const last = latest();
    return found?.currentVersion && last && found.currentVersion > last.version ? found.currentVersion : undefined;
  };
  // (what the item is now, for the restore dialog: read when the restore was asked for)
  const now = (): Now => {
    const version = unrecorded();
    if (version !== undefined) return { state: "unrecorded", version };
    const last = latest();
    // (not met: a selected version has content, so the latest with content is at least that one)
    if (!last) return { state: "unreadable", reason: t("history_restore_no_latest", "No version with content is recorded.") };
    const content = versions()[last.version]?.content;
    if (content) return { state: "known", content };
    const error = unreadable()[last.version];
    return error === undefined ? { state: "reading" } : { state: "unreadable", reason: reasonOf(error) };
  };
  const isCurrent = () => {
    const found = listing();
    return selected() !== undefined && found?.currentVersion === selected() && latest()?.version === selected();
  };

  const toggle = () => {
    const opening = !untrack(open);
    setOpen(opening);
    if (opening) void load();
  };
  const choose = (version: number) => {
    // (clicking the one that is out puts it back)
    if (untrack(selected) === version) {
      setSelected(undefined);
      return;
    }
    setSelected(version);
    want(version);
  };
  const startRestore = () => {
    const last = untrack(latest);
    if (last) want(last.version);
    setConfirming(true);
  };
  const confirm = async () => {
    const version = untrack(selected);
    const current = untrack(listing)?.currentVersion;
    if (version === undefined || current === undefined || current === null || untrack(now).state === "reading") return;
    setBusy(true);
    try {
      const restored = await restoreVersion(api, type, id, version, current);
      setConfirming(false);
      setSelected(undefined);
      setVersions({});
      toasts?.show(
        t("history_restored", "Restored version {version} as version {now}", {
          version: String(version),
          now: String(restored.version),
        }),
        "success",
      );
      // (the item's page reads it again, and the panel its versions)
      void revalidate();
      void load(restored.version);
    } catch (error) {
      console.error(error);
      const stale = error instanceof ApiError && error.status === 412;
      toasts?.show(
        stale
          ? t("history_restore_stale", "Not restored: it was changed meanwhile. The versions are shown again.")
          : t("history_restore_refused", "Not restored: {reason}", { reason: reasonOf(error) }),
        "error",
      );
      setConfirming(false);
      void load();
    } finally {
      setBusy(false);
    }
  };

  // Escape puts the version back, then closes the panel (the dialog has its own)
  onSettled(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || untrack(confirming) || !untrack(open)) return;
      if (untrack(selected) !== undefined) setSelected(undefined);
      else setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  return (
    <>
      <ConsoleButton label={t("history_button", "History")} pressed={open()} onClick={toggle}>
        <span class="flex" data-testid="history-button">
          <HistoryIcon class="size-5" />
        </span>
      </ConsoleButton>
      <HistoryPanel
        model={props.model}
        listing={listing()}
        error={failed()}
        open={open()}
        onClose={() => setOpen(false)}
        selected={selected()}
        onSelect={choose}
        compareHref={`/${encodeURIComponent(type)}/${encodeURIComponent(id)}/history`}
      />
      <VersionDrawer
        open={open() && selected() !== undefined}
        record={record()}
        version={selected() !== undefined ? versions()[selected()!] : undefined}
        error={selected() !== undefined ? unreadable()[selected()!] : undefined}
        current={isCurrent()}
        onRestore={startRestore}
        onClose={() => setSelected(undefined)}
      />
      <Show when={confirming() && selected() !== undefined && versions()[selected()!]}>
        {(target) => (
          <RestoreDialog
            type={type}
            version={target().version}
            undone={undone(listing()!, target().version)}
            now={now()}
            restored={target().content}
            busy={busy()}
            onConfirm={() => void confirm()}
            onClose={() => setConfirming(false)}
          />
        )}
      </Show>
    </>
  );
}

/**
 * The history button in the console of an item's page (a `consoleActions` entry), which opens the panel of its
 * versions. For someone logged in (the history API needs a login), on the item's page only: a restore under a form
 * with changes not saved would lose them.
 */
export default function HistoryAction(props: ConsoleActionProps) {
  return (
    <Show when={props.page === "item" && userIsLoggedIn()}>
      <Show when={props.id} keyed>
        {(id) => <History type={props.type} id={id} model={props.model} />}
      </Show>
    </Show>
  );
}
