import { Title } from "@solidjs/meta";
import { useModels, useTranslations } from "../context";
import { pluralNameOf, shortenLabel } from "../schema";
import { readableName } from "./NavBar";

/**
 * The title of the browser's window, from the most particular part to the project: `Edit | Maximilian | Person | Project`.
 * The last one on the page to be made is the one that counts, so a page can give the type at once and the label when it has come.
 */
export function PageTitle(props: {
  /** What is being done, if it is not looking at it: New, Edit, History */
  action?: string;
  /** The item's label, shortened here */
  label?: string;
  /** The name of a model */
  type?: string;
  /** The type in the plural: a list of them */
  plural?: boolean;
  /** Where a page that is not of a type is: Calendar, Review */
  section?: string;
}) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const typeName = () => {
    if (!props.type) return undefined;
    return props.plural ? pluralNameOf(modelName, props.type) : modelName(props.type);
  };
  const text = () =>
    [
      props.action,
      props.label ? shortenLabel(props.label) : undefined,
      typeName(),
      props.section,
      definitions.projectName ? readableName(definitions.projectName) : "Pangloss",
    ]
      .filter(Boolean)
      .join(" | ");
  return <Title>{text()}</Title>;
}
