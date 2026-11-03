import { getModel, kindTint, plainTint, useModels, useTranslations } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import { shorten, showPart, splitReferences } from "../parts";
import type { Part } from "../parts";

/**
 * A reference to a part of the document, inline in a comment: a small chip with its type and label, which shows the
 * part on the page when clicked. While the parts are being read it shows what is known (the label the comment kept, or
 * the start of the id); a part no longer in the document is struck through and says so.
 */
export function PartChip(props: { id: string; parts?: Part[]; label?: string | null }) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const part = () => props.parts?.find((p) => p.id === props.id);
  const gone = () => props.parts !== undefined && part() === undefined;
  const label = () => shorten(part()?.label ?? props.label ?? `#${props.id.slice(0, 8)}…`, 32);
  return (
    <Show
      when={!gone()}
      fallback={
        <span
          class="mx-0.5 inline-flex items-center gap-1 rounded-sm border-[0.5px] border-slate-400/70 bg-white/80 px-1 py-px align-middle text-xs leading-4 text-slate-500"
          data-testid="review-ref"
          data-gone="true"
        >
          <span class="line-through">{label()}</span>
          <span>{t("review_part_gone", "(no longer there)")}</span>
        </span>
      }
    >
      <button
        type="button"
        class="mx-0.5 inline-flex cursor-pointer items-stretch overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-white align-middle text-xs leading-4 text-slate-800 hover:brightness-95"
        title={t("review_part_show", "Show it on the page")}
        data-testid="review-ref"
        data-ref={props.id}
        onClick={() => showPart(props.id)}
      >
        <Show when={part()}>
          {(found) => (
            <span
              class={[
                "flex items-center px-1 text-[0.6rem] font-semibold uppercase",
                // (a kind with no tint of its own, a reified relation, is grey, as the item page has it)
                kindTint(
                  getModel(definitions, found().type)?.kind ?? "Document",
                  getModel(definitions, found().type)?.interfaceMeta?.colour,
                ) || plainTint,
              ]}
            >
              {modelName(found().type)}
            </span>
          )}
        </Show>
        <span class="flex items-center px-1 py-px">{label()}</span>
      </button>
    </Show>
  );
}

/**
 * The text of a comment, with its references to parts (`#<id>`) as chips where they are. A comment made with a part
 * of its own but no reference to it in its text (made through the API with `targetId`) has the chip first.
 */
export function CommentText(props: {
  text: string;
  parts?: Part[];
  targetId?: string | null;
  targetLabel?: string | null;
}) {
  const pieces = () => splitReferences(props.text);
  const leading = () =>
    props.targetId && !pieces().some((piece) => typeof piece !== "string" && piece.id === props.targetId)
      ? props.targetId
      : undefined;
  // (the label the server kept is the target's: the others are looked up in the parts)
  const keptLabel = (id: string) => (id === props.targetId ? props.targetLabel : undefined);
  return (
    <>
      <Show when={leading()}>
        {(id) => (
          <>
            <PartChip id={id()} parts={props.parts} label={props.targetLabel} />{" "}
          </>
        )}
      </Show>
      <For each={pieces()}>
        {(piece) => (
          <Show when={typeof piece !== "string" && piece} fallback={piece as string}>
            {(reference) => <PartChip id={reference().id} parts={props.parts} label={keptLabel(reference().id)} />}
          </Show>
        )}
      </For>
    </>
  );
}
