import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { ApiError, citedBy, getItem } from "../api";
import type { CitedBy, CitingDocument } from "../api";
import {
  SearchAddressProvider,
  useApi,
  useComponent,
  useCurrentUser,
  useModels,
  useSessionKey,
  useTranslations,
} from "../context";
import { badgeClass, buttonClass } from "../primitives";
import { getModel } from "../schema";
import type { ModelDefinitions } from "../types";
import { GlobalSearch } from "./GlobalSearch";

/** The class of the node a citation is (`Cites[T]`, `pangloss_models.citations`) */
export const CITATION = "PGCitation";

type Data = Record<string, unknown>;

const text = (value: unknown): string | undefined =>
  typeof value === "string" && value !== "" ? value : undefined;

/** Where a cited document is: its own page, or its document's with the part on show */
export function citedHref(headType: string, headId: string, targetId: string): string {
  const page = `/${encodeURIComponent(headType)}/${encodeURIComponent(headId)}`;
  return headId === targetId ? page : `${page}?show=${encodeURIComponent(targetId)}`;
}

/** The classes a citation may be of where these are allowed: each with its subclasses */
export function citableTypes(definitions: ModelDefinitions, cites: string[]): Set<string> {
  const found = new Set<string>();
  for (const name of cites) {
    for (const concrete of getModel(definitions, name)?.concreteTypes ?? [name]) found.add(concrete);
  }
  return found;
}

/** What may be cited in a document: itself and its parts, of the classes allowed, each with the semantic spaces round it */
export interface Citable {
  type: string;
  id: string;
  label: string;
  spaces: string[];
}

/** The document `item` and the documents inside it that are of one of the `types`, in the order they are in */
export function citableParts(definitions: ModelDefinitions, item: Data, types: Set<string>): Citable[] {
  const found: Citable[] = [];
  const visit = (value: unknown, spaces: string[]) => {
    if (Array.isArray(value)) {
      for (const one of value) visit(one, spaces);
      return;
    }
    if (typeof value !== "object" || value === null) return;
    const data = value as Data;
    const type = text(data.type);
    const model = type ? getModel(definitions, type) : undefined;
    // (an entity is referred to, not part of the document; a citation is of another document)
    if (model?.kind === "Entity" || type === CITATION) return;
    const id = text(data.id);
    if (type && id && types.has(type)) {
      found.push({ type, id, label: text(data.label) ?? "", spaces });
    }
    const inside = model?.kind === "SemanticSpace" && type ? [...spaces, type] : spaces;
    for (const [key, held] of Object.entries(data)) {
      if (key !== "meta" && typeof held === "object") visit(held, inside);
    }
  };
  visit(item, []);
  return found;
}

/**
 * A citation of a document (`Cites[T]`): what is cited as a chip, with the semantic spaces round it, and the document
 * it is in as another; or that it has been removed since, or is in a document not yet published. A mark says that
 * what is cited has been changed since. In a form it has a remove button, and "seen" takes the mark off.
 */
export function CitationChips(props: {
  value: Data;
  onRemove?: () => void;
  /** (in a form) The mark is taken off: the citation is of what is there now */
  onSeen?: () => void;
}) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, modelName } = useTranslations();
  const targetType = () => text(props.value.targetType) ?? "";
  const targetId = () => text(props.value.targetId) ?? "";
  const state = () => text(props.value.targetState) ?? "there";
  // (what it was called when it was cited, for one that is gone, or one read from a version in the history)
  const label = () => text(props.value.targetLabel) ?? text(props.value.citedLabel) ?? modelName(targetType());
  const headType = () => text(props.value.targetHeadType);
  const headId = () => text(props.value.targetHeadId);
  const spaces = () => (Array.isArray(props.value.targetSpaces) ? (props.value.targetSpaces as string[]) : []);
  const removeLabel = () => t("citation_remove", "Remove the citation of “{label}”", { label: label() });
  return (
    <span class="flex max-w-full min-w-0 basis-full flex-wrap items-center gap-2" data-citation={targetId()}>
      <Show
        when={state() === "there"}
        fallback={
          <Show
            when={state() === "hidden"}
            fallback={
              <>
                <ReferenceChip
                  type={targetType()}
                  label={label()}
                  onRemove={props.onRemove}
                  removeLabel={removeLabel()}
                />
                <span class={`${badgeClass} border-red-800/50 text-red-900`}>
                  {t("citation_removed", "removed since cited")}
                </span>
              </>
            }
          >
            <span class="text-sm text-slate-600 italic">
              {t("citation_hidden", "Something in a document that is not yet published")}
            </span>
            <Show when={props.onRemove}>
              <button type="button" class={buttonClass("danger", "sm")} onClick={() => props.onRemove?.()}>
                {t("remove", "Remove")}
              </button>
            </Show>
          </Show>
        }
      >
        <ReferenceChip
          type={targetType()}
          label={label()}
          href={headType() && headId() ? citedHref(headType()!, headId()!, targetId()) : undefined}
          spaces={spaces()}
          onRemove={props.onRemove}
          removeLabel={removeLabel()}
        />
        <Show when={headType() && headId() && headId() !== targetId()}>
          <span class="text-sm text-slate-600">{t("citation_in", "in")}</span>
          <ReferenceChip
            type={headType()!}
            label={text(props.value.targetHeadLabel) ?? modelName(headType()!)}
            href={`/${encodeURIComponent(headType()!)}/${encodeURIComponent(headId()!)}`}
          />
        </Show>
      </Show>
      <Show when={props.value.changedSinceCited === true && state() === "there"}>
        <span class={`${badgeClass} border-amber-700/60 text-amber-900`}>
          {t("citation_changed", "changed since cited")}
        </span>
        <Show when={props.onSeen}>
          <button
            type="button"
            class={buttonClass("ordinary", "sm")}
            title={t("citation_seen_help", "Cite it as it is now: the mark goes when this is saved")}
            onClick={() => props.onSeen?.()}
          >
            {t("citation_seen", "Seen")}
          </button>
        </Show>
      </Show>
    </span>
  );
}

/**
 * Chooses what a citation cites: a search of every document by its label, and then, of the one chosen, the document
 * itself or one of its parts, of the classes the relation allows.
 */
export function CitationPicker(props: {
  /** The classes that may be cited (as the relation says: each with its subclasses) */
  cites: string[];
  onPick: (cited: Data) => void;
  onRemove?: () => void;
}) {
  const api = useApi();
  const definitions = useModels();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, modelName } = useTranslations();
  const types = createMemo(() => citableTypes(definitions, props.cites));
  const [chosen, setChosen] = createSignal<{ type: string; id: string; label: string }>();
  const parts = createMemo(() => {
    const head = chosen();
    if (!head) return undefined;
    // (read before the answer is waited for: what is read after is not followed)
    const allowed = types();
    return getItem(api, head.type, head.id, { incomingLimit: 0, extras: false }).then((item) => ({
      head,
      found: citableParts(definitions, item as Data, allowed),
    }));
  });
  const pick = (head: { type: string; id: string; label: string }, part: Citable) =>
    props.onPick({
      type: CITATION,
      targetId: part.id,
      targetType: part.type,
      targetLabel: part.label,
      targetHeadId: head.id,
      targetHeadType: head.type,
      targetHeadLabel: head.label,
      targetSpaces: part.spaces,
      targetState: "there",
      changedSinceCited: false,
    });
  return (
    <div
      class="flex w-full min-w-0 flex-col gap-3 rounded-xs border-[0.5px] border-slate-400/70 p-3"
      data-citation-picker
    >
      <div class="flex items-center justify-between gap-3">
        <span class="text-sm text-slate-700">
          {t("citation_pick", "Cite a {types}: find the document it is in", {
            types: props.cites.map((name) => modelName(name)).join(", "),
          })}
        </span>
        <Show when={props.onRemove}>
          <button type="button" class={buttonClass("ordinary", "sm")} onClick={() => props.onRemove?.()}>
            {t("cancel", "Cancel")}
          </button>
        </Show>
      </div>
      <Show
        when={chosen()}
        fallback={
          // (its search is its own: not the address of the page, which the form is at)
          <SearchAddressProvider value={null}>
            <GlobalSearch
              limit={8}
              onPick={(item) => setChosen({ type: item.type, id: item.id, label: item.label })}
            />
          </SearchAddressProvider>
        }
      >
        <div class="flex flex-wrap items-center gap-2">
          <ReferenceChip type={chosen()!.type} label={chosen()!.label} />
          <button type="button" class={buttonClass("ordinary", "sm")} onClick={() => setChosen(undefined)}>
            {t("citation_another", "Another document")}
          </button>
        </div>
        <Errored
          fallback={(error) => (
            <p role="alert" class="text-sm text-red-800">
              {error() instanceof ApiError ? (error() as ApiError).detail : String(error())}
            </p>
          )}
        >
          <Loading fallback={<p class="text-sm text-slate-600">{t("loading", "Loading…")}</p>}>
            <Show when={parts()}>
              {(loaded) => (
                <Show
                  when={loaded().found.length > 0}
                  fallback={
                    <p class="text-sm text-slate-600">
                      {t("citation_nothing", "Nothing in this document can be cited here.")}
                    </p>
                  }
                >
                  <ul class="flex flex-col items-start gap-2">
                    <For each={loaded().found}>
                      {(part) => (
                        <li class="flex max-w-full min-w-0 items-center gap-2">
                          <button
                            type="button"
                            class={buttonClass("ordinary", "sm")}
                            aria-label={t("citation_cite_named", "Cite “{label}”", {
                              label: part.label || modelName(part.type),
                            })}
                            onClick={() => pick(loaded().head, part)}
                          >
                            {t("citation_cite", "Cite")}
                          </button>
                          <ReferenceChip
                            type={part.type}
                            label={part.label || modelName(part.type)}
                            spaces={part.spaces}
                          />
                        </li>
                      )}
                    </For>
                  </ul>
                </Show>
              )}
            </Show>
          </Loading>
        </Errored>
      </Show>
    </div>
  );
}

interface CitedPart {
  target: string;
  label: string | null;
  by: CitedBy[];
}

const byPart = (rows: CitedBy[]): CitedPart[] => {
  const parts = new Map<string, CitedPart>();
  for (const row of rows) {
    const part = parts.get(row.target) ?? { target: row.target, label: row.targetLabel, by: [] };
    part.by.push(row);
    parts.set(row.target, part);
  }
  return [...parts.values()];
};

/**
 * Says, of a document, which of it is cited as evidence and by what: a line for the document or each part that is
 * cited, with the citing documents as chips. Nothing for a document that nothing cites. In a form (`editing`) it
 * also says what that means for a change.
 */
export function CitedByNotice(props: { type: string; id: string; editing?: boolean }) {
  const api = useApi();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const session = useSessionKey();
  const rows = createMemo(() => {
    session();
    return citedBy(api, props.type, props.id).catch(() => [] as CitedBy[]);
  });
  return (
    <Loading fallback={null}>
      <Show when={rows().length > 0}>
        <section
          class="flex flex-col gap-2 rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100/60 p-3 text-sm"
          aria-label={t("cited_heading", "Cited as evidence")}
          data-cited-by
        >
          <h2 class="font-semibold">{t("cited_heading", "Cited as evidence")}</h2>
          <Show when={props.editing}>
            <p class="text-slate-700">
              {t(
                "cited_editing",
                "Other documents cite what is listed here. A change to it has to be confirmed when you save, and marks each citation as changed; it cannot be removed while it is cited.",
              )}
            </p>
          </Show>
          <ul class="flex flex-col gap-2">
            <For each={byPart(rows())}>
              {(part) => (
                <li class="flex flex-wrap items-center gap-2">
                  <span>
                    {part.target === props.id
                      ? t("cited_whole", "This document, by")
                      : t("cited_part", "“{label}”, by", { label: part.label ?? "…" })}
                  </span>
                  <For each={part.by}>
                    {(row) => (
                      <Show
                        when={!row.hidden && row.type && row.id}
                        fallback={
                          <span class="text-slate-600 italic">
                            {t("cited_hidden", "a document not yet published")}
                          </span>
                        }
                      >
                        <ReferenceChip
                          type={row.type!}
                          label={row.label ?? ""}
                          href={`/${encodeURIComponent(row.type!)}/${encodeURIComponent(row.id!)}`}
                        />
                        <Show when={row.changed}>
                          <span class={`${badgeClass} border-amber-700/60 text-amber-900`}>
                            {t("citation_changed", "changed since cited")}
                          </span>
                        </Show>
                      </Show>
                    )}
                  </For>
                </li>
              )}
            </For>
          </ul>
        </section>
      </Show>
    </Loading>
  );
}

/**
 * Asks before a save that changes what other documents cite: says which documents, and saves with the citations
 * acknowledged, or not at all. What would be removed cannot be saved, but by an admin.
 */
export function CitedDialog(props: {
  changed: CitingDocument[];
  removed: CitingDocument[];
  onSave: (acknowledge: "changes" | "removals") => void;
  onClose: () => void;
}) {
  const Modal = useComponent("Modal");
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const admin = () => useCurrentUser()?.admin === true;
  const list = (rows: CitingDocument[]) => (
    <ul class="flex flex-col gap-2">
      <For each={rows}>
        {(row) => (
          <li class="flex flex-wrap items-center gap-2">
            <span>{t("cited_part", "“{label}”, by", { label: row.targetLabel ?? "…" })}</span>
            <ReferenceChip
              type={row.type}
              label={row.label}
              href={`/${encodeURIComponent(row.type)}/${encodeURIComponent(row.id)}`}
            />
          </li>
        )}
      </For>
    </ul>
  );
  return (
    <Modal title={t("cited_dialog_title", "Cited as evidence")} onClose={props.onClose}>
      <div class="flex flex-col gap-4 p-4 text-sm" data-cited-dialog>
        <Show when={props.removed.length > 0}>
          <p role="alert">
            <span class="font-semibold">{t("cited_removed_lead", "Not saved.")}</span>{" "}
            {t(
              "cited_removed_text",
              "This would remove what other documents cite as evidence. Change those citations first.",
            )}
          </p>
          {list(props.removed)}
        </Show>
        <Show when={props.changed.length > 0}>
          <p role="alert">
            <span class="font-semibold">{t("cited_changed_lead", "Not saved yet.")}</span>{" "}
            {t(
              "cited_changed_text",
              "This changes what other documents cite as evidence. If you save, each citation is marked “changed since cited”.",
            )}
          </p>
          {list(props.changed)}
        </Show>
        <div class="flex justify-end gap-2">
          <button type="button" class={buttonClass("ordinary", "md")} onClick={props.onClose} autofocus>
            {t("cancel", "Cancel")}
          </button>
          <Show when={props.removed.length === 0}>
            <button type="button" class={buttonClass("danger", "md")} onClick={() => props.onSave("changes")}>
              {t("cited_save_anyway", "Save anyway")}
            </button>
          </Show>
          <Show when={props.removed.length > 0 && admin()}>
            <button type="button" class={buttonClass("danger", "md")} onClick={() => props.onSave("removals")}>
              {t("cited_remove_anyway", "Remove anyway (admin)")}
            </button>
          </Show>
        </div>
      </div>
    </Modal>
  );
}
