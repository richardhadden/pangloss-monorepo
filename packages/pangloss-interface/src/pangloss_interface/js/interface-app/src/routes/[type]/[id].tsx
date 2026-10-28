import { useComponent } from "@pangloss/interface-core";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, Loading } from "solid-js";
import { itemQuery } from "../../queries";

// One Document or Entity: /Person/<id>
export default function EntityPage(props: RouteProps<"/:type/:id">) {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const item = createMemo(() => itemQuery(props.params.type, props.params.id));
  return (
    <main>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          {/* (the type is the item's own, which can be a subtype of the one in the address) */}
          <Console type={item().type} label={item().label ?? item().id} />
          <h1>{item().label ?? item().id}</h1>
        </Loading>
      </Errored>
    </main>
  );
}
