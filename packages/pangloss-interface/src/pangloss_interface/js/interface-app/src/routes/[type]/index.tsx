import { useComponent } from "@pangloss/interface-core";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, For, Loading } from "solid-js";
import { listQuery } from "../../queries";

// The list of a type of Document or Entity: /Person
export default function EntityList(props: RouteProps<"/:type">) {
  const FieldList = useComponent("FieldList");
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  // (an async memo: what reads `items()` waits for it, inside the `Loading`)
  const items = createMemo(() => listQuery(props.params.type, "", false, 1));
  return (
    <main>
      <Console type={props.params.type} list />
      <h1>{props.params.type}</h1>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          <p>{items().count} found</p>
          <ul>
            <For each={items().results}>
              {(item) => (
                <li>
                  <a href={`/${item.type}/${item.id}`}>{item.label}</a>
                </li>
              )}
            </For>
          </ul>
        </Loading>
      </Errored>
      <FieldList model={props.params.type} />
    </main>
  );
}
