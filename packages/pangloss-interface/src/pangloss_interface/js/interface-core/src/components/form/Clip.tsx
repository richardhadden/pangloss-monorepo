import { createMemo, For, Show } from "solid-js";
import type { Accessor } from "solid-js";
import { useClipboard, useItemForm, useModels, useTranslations } from "../../context";
import type { ClipEntry } from "../../context";
import { kindTint } from "../../primitives";
import { clipValue, fitEdge, fitsEmbedded, fitsRelation, forPaste, getModel, nodeIds } from "../../schema";
import type { Env, FormData, Path } from "../../schema";
import type { EmbeddedField, RelationOption } from "../../types";
import { plainTint } from "./styles";

export function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current stroke-2" aria-hidden="true">
      <rect x="8" y="8" width="12" height="12" rx="1.5" />
      <path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" />
    </svg>
  );
}

export function CutIcon() {
  return (
    <svg viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current stroke-2" stroke-linecap="square" aria-hidden="true">
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="18" r="2.5" />
      <path d="M7.8 16.2L18 4M16.2 16.2L6 4" />
    </svg>
  );
}

/**
 * The cut button if `onCut` is given, then the copy button, of something that can go on the
 * clipboard, each with `buttonClass` (to fit the bar or frame they are joined on to)
 */
export function ClipButtons(props: {
  name: string;
  buttonClass: string;
  onCopy: () => void;
  onCut?: () => void;
}) {
  const { t } = useTranslations();
  return (
    <>
      <Show when={props.onCut}>
        <button
          type="button"
          class={props.buttonClass}
          aria-label={t("cut_item", "Cut {name}", { name: props.name })}
          title={t("cut_item", "Cut {name}", { name: props.name })}
          onClick={() => props.onCut?.()}
        >
          <CutIcon />
        </button>
      </Show>
      <button
        type="button"
        class={props.buttonClass}
        aria-label={t("copy_item", "Copy {name}", { name: props.name })}
        title={t("copy_item", "Copy {name}", { name: props.name })}
        onClick={() => props.onCopy()}
      >
        <CopyIcon />
      </button>
    </>
  );
}

/**
 * What puts the thing at `path` of the form on the clipboard: `copy`, and `cut` (copy, then
 * `remove`). Nothing without a clipboard. `edgeModel`: for an entity, the model of the
 * properties of the relation it is in.
 */
export function useClipActions(
  path: Accessor<Path>,
  remove: () => void,
  edgeModel?: Accessor<string | null | undefined>,
): { copy: () => void; cut: () => void } | undefined {
  const clipboard = useClipboard();
  const form = useItemForm();
  const definitions = useModels();
  if (!clipboard) return undefined;
  const put = (cut: boolean) => {
    const value = form.get(path());
    if (typeof value !== "object" || value === null || Array.isArray(value)) return;
    clipboard.put({
      value: JSON.parse(JSON.stringify(clipValue(definitions, value as FormData))) as FormData,
      cut,
      source: form.headId,
      edgeModel: edgeModel?.(),
    });
  };
  return {
    copy: () => put(false),
    cut: () => {
      put(true);
      remove();
    },
  };
}

/** The label of something on the clipboard: its own, or the name of its type */
export function ClipLabel(props: { value: FormData; class?: string }) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const type = () => String(props.value.type ?? "");
  const model = () => getModel(definitions, type());
  return (
    <span class={["inline-flex min-w-0 items-stretch overflow-hidden rounded-xs", props.class]}>
      <span
        class={[
          "flex shrink-0 items-center px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase select-none",
          kindTint(model()?.kind, model()?.interfaceMeta?.colour) || plainTint,
        ]}
      >
        {modelName(type())}
      </span>
      <Show when={typeof props.value.label === "string" && props.value.label !== ""}>
        <span class="min-w-0 truncate px-1.5 py-0.5 text-xs normal-case">{String(props.value.label)}</span>
      </Show>
    </span>
  );
}

/**
 * The place, beside where something new is added, where what is on the clipboard can be pasted:
 * greyed out, with a button for each thing on the clipboard that is allowed here, all that is
 * inside it too (`fits`). Not there when nothing fits.
 */
function PasteSlot(props: {
  fits: (entry: ClipEntry) => boolean;
  /** `value`, made ready for this form, put in place */
  onPaste: (entry: ClipEntry, value: FormData) => void;
}) {
  const clipboard = useClipboard();
  const form = useItemForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const fitting = createMemo(() => (clipboard?.entries() ?? []).filter((entry) => props.fits(entry)));
  const paste = (entry: ClipEntry) => {
    // (into the document it was taken from, it keeps the ids that are not there already)
    const same = form.headId !== undefined && entry.source === form.headId;
    props.onPaste(entry, forPaste(definitions, entry.value, same, nodeIds(definitions, form.plain())));
    clipboard?.pasted(entry.key);
  };
  return (
    <Show when={fitting().length > 0}>
      <div
        role="group"
        aria-label={t("paste_here", "Paste here")}
        class="flex w-full flex-wrap items-center gap-2 rounded-xs border-[0.5px] border-dashed border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-400 uppercase select-none"
      >
        <span>{t("paste_here", "Paste here")}</span>
        <For each={fitting()}>
          {(entry) => (
            <button
              type="button"
              class="flex max-w-full min-w-0 cursor-pointer items-center gap-1 rounded-xs border-[0.5px] border-slate-300 opacity-60 hover:border-slate-500 hover:opacity-100 focus:border-slate-500 focus:opacity-100 focus:outline-none"
              title={t("paste_item", "Paste {name}", {
                name: typeof entry.value.label === "string" ? String(entry.value.label) : String(entry.value.type),
              })}
              onClick={() => paste(entry)}
            >
              {/* (something cut is marked: it goes from the clipboard when it is pasted) */}
              <Show when={entry.cut}>
                <span class="pl-1 text-slate-500">
                  <CutIcon />
                </span>
              </Show>
              <ClipLabel value={entry.value} />
            </button>
          )}
        </For>
      </div>
    </Show>
  );
}

/** A paste slot for a relation with these `options`: what is pasted is given to `onPaste` */
export function RelationPasteSlot(props: {
  options: RelationOption[];
  env: Env;
  onPaste: (value: FormData) => void;
}) {
  const definitions = useModels();
  return (
    <PasteSlot
      fits={(entry) => fitsRelation(definitions, entry.value, props.options, props.env)}
      onPaste={(entry, value) => props.onPaste(fitEdge(value, props.options, props.env, entry.edgeModel))}
    />
  );
}

/** A paste slot for an embedded field with nothing in it */
export function EmbeddedPasteSlot(props: { field: EmbeddedField; onPaste: (value: FormData) => void }) {
  const definitions = useModels();
  return (
    <PasteSlot
      fits={(entry) => fitsEmbedded(definitions, entry.value, props.field)}
      onPaste={(_, value) => props.onPaste(value)}
    />
  );
}

/** The icon of something stashed (a tray with an arrow into it), as on the Stash button */
export function StashIcon(props: { class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["select-none fill-none stroke-current stroke-2", props.class ?? "size-3.5"]}
      stroke-linecap="square"
      aria-hidden="true"
    >
      <path d="M3.5 13.5h4.5l1.5 2.5h5l1.5-2.5h4.5M3.5 13.5l2.5-6h2.5M20.5 13.5l-2.5-6h-2.5M3.5 13.5V19h17v-5.5M12 3.5v8M9 8.5l3 3 3-3" />
    </svg>
  );
}
