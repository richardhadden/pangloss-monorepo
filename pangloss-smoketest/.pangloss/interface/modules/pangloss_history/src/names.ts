import { useTranslations } from "@pangloss/interface-core";
import type { ModelDefinition } from "@pangloss/interface-core";

/** The name of a field of a model, by its key, in the language of the page; the label (which the models do not export
 * as a field) as the form calls it */
export function useFieldName() {
  const { t, fieldName } = useTranslations();
  return (model: ModelDefinition, key: string): string => {
    if (key === "label") return t("label", "Label");
    const field = model.fields.find((each) => each.key === key);
    return fieldName(model.name, field?.name ?? key);
  };
}
