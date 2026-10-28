import { useComponent } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, For, isPending, Loading } from "solid-js";
import { listQuery } from "../../queries";

// A parameter of the address that was given more than once is the first
const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

// The list of a type of Document or Entity: /Person
export default function EntityList(props: RouteProps<"/:type">) {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const ResultButton = useComponent("ResultButton");
  // The search is in the address (`?q=rome&deep=1`), so it can be linked to, and the back button
  // goes back through searches. A change of it asks the list again.
  const [search, setSearch] = useSearchParams();
  const text = () => first(search.q) ?? "";
  const deep = () => first(search.deep) === "1";
  // (an async memo: what reads `items()` waits for it, inside the `Loading`; the arguments
  // are read before the query is called, so a change of them runs it again)
  const items = createMemo(() => listQuery(props.params.type, text(), deep(), 1));
  // (true while a change of the search is being answered, the old results still on show)
  const pending = () => isPending(items);
  return (
    <main class="mx-auto w-full max-w-[100rem] px-6 py-6">
      <Console
        type={props.params.type}
        list
        query={text()}
        deep={deep()}
        // (the same address again, not a new place in the history, for each search)
        onSearch={({ query, deep }) =>
          setSearch({ q: query, deep: deep ? "1" : null }, { replace: true })
        }
        count={items().count}
        pending={pending()}
      />
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          <ul class={["flex flex-col gap-2 transition-opacity", { "opacity-50": pending() }]}>
            <For each={items().results}>
              {(item) => (
                <li>
                  <ResultButton href={`/${item.type}/${item.id}`} type={item.type} label={item.label} />
                </li>
              )}
            </For>
          </ul>
        </Loading>
      </Errored>
    </main>
  );
}
