import { DefaultReferenceChip, useTranslations } from "@pangloss/interface-core";
import type { ViewCardProps } from "@pangloss/interface-core";
import { Show } from "solid-js";

// A type wherever it is part of something else: as a reference (a field of an item that has it), the
// interface's own chip, as it is in a form; as a result, its label, marked as a type. It draws the item
// itself: the interface's own button for the model would ask for this card again.
export default function TypeCard(props: ViewCardProps) {
  const { t, modelName } = useTranslations();
  return (
    <Show
      when={props.context !== "reference"}
      fallback={
        <DefaultReferenceChip
          type={props.type}
          label={props.label}
          href={props.href ?? `/${props.type}/${props.id ?? ""}`}
        />
      }
    >
      <a
        href={props.href ?? `/${props.type}/${props.id ?? ""}`}
        class="flex w-full items-center gap-3 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70 px-4 py-3 text-sm hover:bg-slate-200/70"
      >
        <span class="text-xs font-semibold uppercase">{modelName(props.type)}</span>
        <span class="rounded-sm border-[0.5px] border-slate-400/70 px-1 text-[0.65rem] uppercase text-slate-600">
          {t("type_marker", "type")}
        </span>
        <span class="min-w-0 truncate">{props.label}</span>
      </a>
    </Show>
  );
}
