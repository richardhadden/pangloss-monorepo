import { kindRule, kindTint, useTranslations } from "@pangloss/interface-core";
import type { ModelDefinition } from "@pangloss/interface-core";

/**
 * The type at the front of a chip, as a reference chip has it: the name of the model, in its kind's tint (or its
 * colour). For a chip with a frame of its own: a rule on its right only.
 */
export function TypeTag(props: { model: Pick<ModelDefinition, "name" | "kind" | "interfaceMeta"> }) {
  const { modelName } = useTranslations();
  return (
    <span
      data-type-tag
      class={[
        "flex shrink-0 items-center border-r-[0.5px] px-2.5 text-xs font-semibold uppercase select-none",
        kindTint(props.model.kind, props.model.interfaceMeta?.colour),
        kindRule(props.model.kind, props.model.interfaceMeta?.colour),
      ]}
    >
      {modelName(props.model.name)}
    </span>
  );
}
