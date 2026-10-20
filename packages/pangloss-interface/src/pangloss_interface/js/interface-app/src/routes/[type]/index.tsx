import { useComponent } from "@pangloss/interface-core";
import type { RouteProps } from "@solidjs/router";

// The list of a type of Document or Entity: /Person
export default function EntityList(props: RouteProps<"/:type">) {
  const FieldList = useComponent("FieldList");
  return (
    <main>
      <h1>{props.params.type}</h1>
      <FieldList model={props.params.type} />
    </main>
  );
}
