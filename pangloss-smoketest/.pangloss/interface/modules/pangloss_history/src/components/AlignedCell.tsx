import {
  getModel,
  headBarClass,
  headLabelClass,
  headRestClass,
  ItemValue,
  kindRule,
  kindTint,
  plainTint,
  typeChipClass,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import { For, Match, Show, Switch } from "solid-js";
import type { AlignedRow, Mark } from "../align";
import { wordDiff } from "../words";

type Data = Record<string, unknown>;

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// (whole class names, so that Tailwind finds them)
/** The background of a cell of the compare page, by how it differs from the one to its left */
export const CELL_TONE: Record<Mark, string> = {
  same: "",
  absent: "bg-[repeating-linear-gradient(135deg,transparent_0_6px,rgb(148_163_184/0.14)_6px_7px)]",
  added: "bg-green-50 shadow-[inset_3px_0_0_var(--color-green-500)]",
  removed:
    "bg-red-50 bg-[repeating-linear-gradient(135deg,transparent_0_6px,rgb(239_68_68/0.12)_6px_7px)] shadow-[inset_3px_0_0_var(--color-red-500)]",
  changed: "bg-amber-50 shadow-[inset_3px_0_0_var(--color-amber-500)]",
};

const WORD_TONE = {
  same: "",
  added: "rounded-[2px] bg-green-200/80 text-green-950",
  removed: "rounded-[2px] bg-red-200/80 text-red-950 line-through decoration-red-600/60",
};

/** The words of a text that changed: those taken out struck through in red, those put in green */
export function Words(props: { before: string; after: string }) {
  return (
    <span class="w-full text-sm break-words whitespace-pre-wrap" data-testid="history-words">
      <For each={wordDiff(props.before, props.after)}>
        {(piece) => (
          <span class={WORD_TONE[piece.kind]} data-kind={piece.kind}>
            {piece.text}
          </span>
        )}
      </For>
    </span>
  );
}

/** A part as a head: an entity's chip, or the type (a chip in its colour) and the label of a nested part */
export function PartHead(props: { value: unknown; row: AlignedRow }) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const type = () => (isObject(props.value) && typeof props.value.type === "string" ? props.value.type : "");
  const model = () => getModel(definitions, type());
  return (
    <Show
      when={!props.row.entity}
      fallback={
        <div class={{ "opacity-60": isObject(props.value) && props.value.missing === true }}>
          <ItemValue value={props.value} field={props.row.field} />
        </div>
      }
    >
      <div class={[headBarClass, "w-full"]}>
        <span
          class={[
            typeChipClass,
            kindTint(model()?.kind, model()?.interfaceMeta?.colour) || plainTint,
            kindRule(model()?.kind, model()?.interfaceMeta?.colour),
          ]}
        >
          {modelName(type())}
        </span>
        <span class={headRestClass}>
          <Show when={isObject(props.value) && typeof props.value.label === "string"}>
            <span class={headLabelClass}>{(props.value as Data).label as string}</span>
          </Show>
        </span>
      </div>
    </Show>
  );
}

/** What a row holds in one version: its value, or its part's head */
export function RowValue(props: { row: AlignedRow; value: unknown }) {
  return (
    <Show when={props.value !== undefined}>
      <Show when={props.row.kind === "head"} fallback={<ItemValue value={props.value} field={props.row.field} />}>
        <PartHead value={props.value} row={props.row} />
      </Show>
    </Show>
  );
}

/**
 * The value of a row in version `index`, showing how it differs from the version before: the words of a text, or what
 * it was (struck through) and what it is
 */
export function ChangedValue(props: { row: AlignedRow; index: number }) {
  const before = () => (props.index > 0 ? props.row.cells[props.index - 1]!.value : undefined);
  const here = () => props.row.cells[props.index]!.value;
  const mark = () => props.row.cells[props.index]!.mark;
  return (
    <Switch fallback={<RowValue row={props.row} value={here()} />}>
      <Match when={mark() === "changed" && typeof before() === "string" && typeof here() === "string"}>
        <Words before={before() as string} after={here() as string} />
      </Match>
      <Match when={mark() === "changed"}>
        <div class="flex w-full min-w-0 flex-col gap-1.5">
          <div class="flex min-w-0 flex-wrap gap-2 opacity-60 line-through decoration-red-600/60" data-testid="history-was">
            <RowValue row={props.row} value={before()} />
          </div>
          <div class="flex min-w-0 flex-wrap gap-2">
            <RowValue row={props.row} value={here()} />
          </div>
        </div>
      </Match>
      <Match when={mark() === "removed"}>
        <div class="flex min-w-0 flex-wrap gap-2 opacity-60 line-through decoration-red-600/60" data-testid="history-was">
          <RowValue row={props.row} value={before()} />
        </div>
      </Match>
    </Switch>
  );
}
