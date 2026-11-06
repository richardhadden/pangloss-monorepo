import { Show } from "solid-js";
import { fieldGridClass, fieldRowClass, getModel, ItemValue, useModels, useTranslations } from "@pangloss/interface-core";
import type { ViewCardProps } from "@pangloss/interface-core";

/**
 * A weighted alternative on an item's page (not in the form, which has its own sliders): no head, only what it
 * holds, each with its likelihood at the end of its chip. With several, under the name of the field
 * ("Alternatives"); one alone is only itself.
 */
export default function WeightedAlternativeCard(props: ViewCardProps) {
  const definitions = useModels();
  const { fieldName } = useTranslations();
  const field = () => getModel(definitions, props.type)?.fields.find((each) => each.name === "alternatives");
  const alternatives = () => (Array.isArray(props.item?.alternatives) ? (props.item.alternatives as unknown[]) : []);
  const id = () => (typeof props.item?.id === "string" ? props.item.id : undefined);
  return (
    <Show
      when={alternatives().length > 1}
      fallback={
        <span class="inline-flex min-w-0 flex-wrap gap-2" data-item-id={id()}>
          <ItemValue value={alternatives()} field={field()} />
        </span>
      }
    >
      <dl class={["w-full", fieldGridClass]} data-item-id={id()}>
        <div class={fieldRowClass}>
          <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">{fieldName(props.type, "alternatives")}</dt>
          <dd class="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-4">
            <ItemValue value={alternatives()} field={field()} />
          </dd>
        </div>
      </dl>
    </Show>
  );
}
