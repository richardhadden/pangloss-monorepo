import { useComponent, wrappingSpaces } from "@pangloss/interface-core";
import type { ContextLabel } from "@pangloss/interface-core";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, Loading } from "solid-js";
import { itemQuery } from "../queries";

// One Document or Entity: /Person/<id>
export default function EntityPage(props: RouteProps<"/:type/:id">) {
  const Console = useComponent("Console");
  const ItemContents = useComponent("ItemContents");
  const ErrorMessage = useComponent("ErrorMessage");
  const item = createMemo(() => itemQuery(props.params.type, props.params.id));
  return (
    <main class="mx-auto w-full max-w-[100rem] px-6 py-6">
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          {/* (the type is the item's own, which can be a subtype of the one in the address) */}
          <Console
            type={item().type}
            label={item().label ?? item().id}
            spaces={wrappingSpaces(item().meta.contextLabels as ContextLabel[] | null | undefined)}
          />
          <h1 class="mb-6 text-xl font-semibold">{item().label ?? item().id}</h1>
          <ItemContents item={item()} />
        </Loading>
      </Errored>
    </main>
  );
}
