import { Customised, useComponent, getModel, useModels, useTranslations, headOf, wrappingSpaces } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, For, isPending, Loading, Show } from "solid-js";
import { listQuery, searchOf } from "../queries";

// The list of a type of Document or Entity: /Person
export default function EntityList(props: RouteProps<"/:type">) {
  // (a model may name a page of an interface module for its list: it replaces this one)
  const definitions = useModels();
  const model = () => getModel(definitions, props.params.type);
  const [search, setSearch] = useSearchParams();
  return (
    <Customised
      slot="listPage"
      type={props.params.type}
      skip={model() === undefined}
      props={{
        type: props.params.type,
        model: model()!,
        search: { query: searchOf(search).q, deep: searchOf(search).deep },
        onSearch: ({ query, deep }) =>
          setSearch({ q: query, deep: deep ? "1" : null }, { replace: true }),
      }}
      fallback={<DefaultList {...props} />}
    />
  );
}

// (an abstract type that no concrete type is below has nothing to list, and the API has no list for it)
function DefaultList(props: RouteProps<"/:type">) {
  const definitions = useModels();
  const listable = () => {
    const model = getModel(definitions, props.params.type);
    return model === undefined || model.concreteTypes.length > 0;
  };
  return (
    <Show when={listable()} fallback={<NothingToList type={props.params.type} />}>
      <ListOfItems {...props} />
    </Show>
  );
}

function NothingToList(props: { type: string }) {
  const Console = useComponent("Console");
  const { t, modelName } = useTranslations();
  return (
    <main class="mx-auto w-full max-w-[100rem] px-6 py-6">
      <Console type={props.type} list />
      <p>
        {t(
          "abstract_no_types",
          "{type} is an abstract type, and no type of it exists in this project: there is nothing to list.",
          { type: modelName(props.type) },
        )}
      </p>
    </main>
  );
}

function ListOfItems(props: RouteProps<"/:type">) {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const ResultButton = useComponent("ResultButton");
  // The search is in the address (`?q=rome&deep=1`), so it can be linked to, and the back button
  // goes back through searches. A change of it asks the list again.
  const [search, setSearch] = useSearchParams();
  const text = () => searchOf(search).q;
  const deep = () => searchOf(search).deep;
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
        truncated={items().truncated}
        pending={pending()}
      />
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          <ul class={["flex flex-col gap-2 transition-opacity", { "opacity-50": pending() }]}>
            <For each={items().results}>
              {(item) => (
                <li>
                  <ResultButton
                    href={`/${item.type}/${item.id}`}
                    type={item.type}
                    label={item.label}
                    spaces={wrappingSpaces(item.meta?.contextLabels)}
                    head={headOf(item)}
                  />
                </li>
              )}
            </For>
          </ul>
        </Loading>
      </Errored>
    </main>
  );
}
