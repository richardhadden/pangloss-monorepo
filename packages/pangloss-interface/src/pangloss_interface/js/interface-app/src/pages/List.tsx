import {
  canBeSearched,
  Customised,
  SearchPanel,
  decodeSearchForm,
  encodeSearchForm,
  createWindowVirtualizer,
  useComponent,
  getModel,
  useModels,
  useStash,
  useTranslations,
  headOf,
  wrappingSpaces,
  Spinner,
} from "@pangloss/interface-core";
import type { Page as ListPage, Summary } from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import {
  createEffect,
  createMemo,
  createSignal,
  Errored,
  For,
  isPending,
  Loading,
  onCleanup,
  Show,
  untrack,
} from "solid-js";
import { LIST_PAGE_SIZE, listQuery, pageOf, searchOf, startOf, requestOf, usesOf } from "../queries";
import type { ListUses } from "../queries";
import { Page } from "../Page";

type ListKey = (key: "next" | "previous" | "open") => void;

// The list of a type of Document or Entity: /Person
export default function EntityList(props: RouteProps<"/:type">) {
  // (a model may name a page of an interface module for its list: it replaces this one)
  const definitions = useModels();
  const model = () => getModel(definitions, props.params.type);
  const [search, setSearch] = useSearchParams();
  // (the stashed items of this type, and of its types, are shown beside the clipboard while the page is about it)
  const stash = useStash();
  createEffect(
    () => props.params.type,
    (type) => stash?.showFor(type),
  );
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
    <Page>
      <Console type={props.type} list />
      <p>
        {t(
          "abstract_no_types",
          "{type} is an abstract type, and no type of it exists in this project: there is nothing to list.",
          { type: modelName(props.type) },
        )}
      </p>
    </Page>
  );
}

function ListOfItems(props: RouteProps<"/:type">) {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const definitions = useModels();
  const { t } = useTranslations();
  // The search is in the address (`?q=rome&deep=1`, and the search form's `?form={...}`), so it can be linked to,
  // and the back button goes back through searches. A change of it asks the list again.
  const [search, setSearch] = useSearchParams();
  const text = () => searchOf(search).q;
  const form = () => searchOf(search).form;
  // (the pattern and order of the search form, with the words typed; "" while the form has neither)
  const request = () => requestOf(props.params.type, form(), text());
  const structured = () => request() !== "";
  // (`InterfaceMeta(list_used_only=...)`: only what something refers to, unless the address has `?all=1`)
  const uses = () => usesOf(definitions, props.params.type, searchOf(search).all);
  const toggleUsed = () => {
    position = 0;
    setSearch({ all: uses() === "used" ? "1" : null, at: null }, { replace: true });
  };
  // (a deep search is not made with the form)
  const deep = () => searchOf(search).deep && !structured();
  // The search form: there if the type has a search pattern, and a search for it can find anything (not a
  // document that is only ever part of another); open at first if the address has one
  const searchable = () =>
    definitions.searchPatterns?.[props.params.type] !== undefined && canBeSearched(definitions, props.params.type);
  const [formOpen, setFormOpen] = createSignal(
    untrack(() => decodeSearchForm(form(), props.params.type) !== undefined),
  );
  // (its code is fetched the first time it is opened, and only then does it slide open, as it would have been there)
  const [panelWanted, setPanelWanted] = createSignal(untrack(formOpen));
  const [panelOpen, setPanelOpen] = createSignal(untrack(formOpen));
  createEffect(formOpen, (open) => {
    if (!open) return void setPanelOpen(false);
    setPanelWanted(true);
    void (SearchPanel as unknown as { preload: () => Promise<unknown> })
      .preload()
      .then(() => requestAnimationFrame(() => setPanelOpen(untrack(formOpen))));
  });
  const toggleForm = () => {
    const opening = !formOpen();
    setFormOpen(opening);
    // (it opens at the top of the page, under the console: the page is taken there to see it)
    if (opening && window.scrollY > 0) window.scrollTo({ top: 0, behavior: "smooth" });
  };
  // (the form the panel last said it holds: one in the address that is not, as after going back, is shown in a new
  // panel, which is a new object here)
  let askedForm = untrack(form);
  const panel = createMemo<object>((previous) => {
    const now = form();
    if (previous && now === askedForm) return previous;
    askedForm = now;
    return {};
  });
  // The item the list is scrolled to: from the address (`?at=`) when the page is opened, then
  // kept by the list as it is scrolled (which writes it in the address without the router), and
  // back to the top for a new search. A list asked again (as after logging in) starts there.
  let position = untrack(() => startOf(search));
  // (an async memo: what reads `first()` waits for it, inside the `Loading`; the arguments
  // are read before the query is called, so a change of them runs it again)
  const first = createMemo(async () => {
    const asked = { type: props.params.type, q: text(), deep: deep(), form: form(), request: request(), uses: uses() };
    const start = position;
    const page = await listQuery(asked.type, asked.q, asked.deep, asked.request, pageOf(start), asked.uses);
    return { ...asked, start, page };
  });
  // (true while a change of the search is being answered, the old results still on show)
  const pending = () => isPending(first);
  // (the search box has the keyboard: the list on show answers its arrows and Enter, and shows what is selected while it has)
  const [searchFocused, setSearchFocused] = createSignal(false);
  let listKey: ListKey | undefined;
  return (
    <Page>
      <Console
        type={props.params.type}
        list
        query={text()}
        deep={deep()}
        // (the same address again, not a new place in the history, for each search; a new one starts at the top)
        onSearch={({ query, deep }) => {
          position = 0;
          setSearch({ q: query, deep: deep ? "1" : null, at: null }, { replace: true });
        }}
        count={first().page.count}
        truncated={first().page.truncated}
        pending={pending()}
        onToggleForm={searchable() ? toggleForm : undefined}
        formOpen={formOpen()}
        onToggleUsed={uses() === "none" ? undefined : toggleUsed}
        showingAll={uses() === "all"}
        structured={structured()}
        onListKey={(key) => listKey?.(key)}
        onFocusChange={setSearchFocused}
      />
      <Show when={searchable()}>
       <Show when={panelWanted()}>
        <Loading>
        <Show when={panel()} keyed>
          {(_panel) => (
            <SearchPanel
              type={props.params.type}
              initial={untrack(() => decodeSearchForm(form(), props.params.type))}
              open={panelOpen()}
              onClose={() => setFormOpen(false)}
              onChange={(changed) => {
                askedForm = encodeSearchForm(changed) ?? "";
                position = 0;
                setSearch({ form: askedForm || null, at: null }, { replace: true });
              }}
            />
          )}
        </Show>
        </Loading>
       </Show>
      </Show>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p class="mx-6 pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
          {/* (a new list for each answer: what was fetched of the last one is not this one) */}
          <Show when={first()} keyed>
            {(answer) => (
              <Results
                {...answer}
                pending={pending()}
                onScrolled={(at) => (position = at)}
                showSelected={searchFocused()}
                keys={(answerKey) => (listKey = answerKey)}
              />
            )}
          </Show>
        </Loading>
      </Errored>
    </Page>
  );
}

// (before it is measured: one line, as `ResultButton` is without spaces round it)
const ROW_HEIGHT = 46;
const ROW_GAP = 8;
// (the console bar is over the top of the window)
const BAR_HEIGHT = 48;
// (how long scrolling has to stop for before where the list is is written in the address)
const SAVE_POSITION_MS = 300;

/** The items of a page, each with how many things refer to it, where that was asked for */
function counted(page: ListPage<Summary>) {
  return page.results.map((item) => ({ ...item, useCount: page.useCounts?.[item.id] }));
}

/**
 * The items of a list, as many as there are, of which only those on show are rendered, and
 * asked for, a page at a time, when they come on show (`start` is the item the list was last
 * scrolled to, whose page is `page`). Where it is scrolled to is kept in the address
 * (`?at=40`), so that going back to the list, or loading it again, starts there.
 */
function Results(props: {
  type: string;
  q: string;
  deep: boolean;
  /** The search form, as in the address, and the request it stands for */
  form: string;
  request: string;
  /** Whether what is used is asked for, and how much is said of it */
  uses: ListUses;
  start: number;
  page: ListPage<Summary>;
  pending: boolean;
  /** Where it has been scrolled to: the first item on show */
  onScrolled: (at: number) => void;
  /** Whether to show which item is selected: while the keyboard is choosing */
  showSelected: boolean;
  /** Given what answers the keys of the search box */
  keys: (key: ListKey) => void;
}) {
  const ResultButton = useComponent("ResultButton");
  const { t } = useTranslations();
  const navigate = useNavigate();
  // (what the list was made from, read once: a new answer is a new list)
  const { type, q, deep, form, request, uses, start, page } = untrack(() => ({ ...props }));
  // The pages fetched so far, by number
  const [pages, setPages] = createSignal(new Map([[page.page, counted(page)]]));
  const asked = new Set([page.page]);
  const virtual = createWindowVirtualizer({
    count: () => page.count,
    estimateSize: ROW_HEIGHT,
    gap: ROW_GAP,
    overscan: 10,
    scrollPaddingStart: BAR_HEIGHT,
    initialIndex: start,
  });
  const itemAt = (index: number) =>
    pages().get(pageOf(index))?.[index % LIST_PAGE_SIZE];

  // The item the search box's keys are on: the first of each new list, which is a new `Results`
  const [selected, setSelected] = createSignal(start);
  untrack(() => props.keys)((key) => {
    if (key === "open") {
      const item = itemAt(selected());
      if (item) navigate(`/${item.type}/${item.id}`);
      return;
    }
    const next = Math.max(0, Math.min(page.count - 1, selected() + (key === "next" ? 1 : -1)));
    setSelected(next);
    virtual.scrollToIndex(next, "auto");
  });

  // Ask for the pages of what is on show that are not here yet
  createEffect(
    () => [...new Set(virtual.items().map((row) => pageOf(row.index)))],
    (needed) => {
      for (const number of needed) {
        if (asked.has(number)) continue;
        asked.add(number);
        listQuery(type, q, deep, request, number, uses).then(
          (fetched) => setPages((old) => new Map(old).set(number, counted(fetched))),
          // (asked again when it next comes on show)
          () => asked.delete(number),
        );
      }
    },
  );

  // Keep where the list is in the address, once scrolling stops (not through the router: it is
  // not a new search, and nothing has to be read again)
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(timer));
  createEffect(virtual.items, () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const url = new URL(window.location.href);
      // (not if the address is already that of another search: this list is on its way out)
      const params = searchOf(Object.fromEntries(url.searchParams));
      if (
        params.q !== q ||
        (params.deep && !request) !== deep ||
        params.form !== form ||
        (uses !== "none" && params.all !== (uses === "all"))
      )
        return;
      const at = virtual.firstVisible();
      props.onScrolled(at);
      if (at > 0) url.searchParams.set("at", String(at));
      else url.searchParams.delete("at");
      if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url);
    }, SAVE_POSITION_MS);
  });

  return (
    <ul
      ref={virtual.setList}
      class={["relative mx-6 transition-opacity", { "opacity-50": props.pending }]}
      style={{ height: `${virtual.totalSize()}px` }}
    >
      <For each={virtual.items()} keyed={(row) => row.key}>
        {(row) => (
          <li
            // (the index is set before it is measured, which reads it; measured once it is rendered,
            // as what that changes is not written while rendering)
            ref={(element) => {
              element.dataset.index = String(untrack(row).index);
              queueMicrotask(() => virtual.measure(element));
            }}
            data-index={row().index}
            class="absolute top-0 left-0 w-full"
            style={{ transform: `translateY(${row().start - virtual.scrollMargin()}px)` }}
          >
            <Show
              when={itemAt(row().index)}
              fallback={
                <div
                  aria-label={t("loading", "Loading…")}
                  class="animate-pulse rounded-xs border-[0.5px] border-slate-300/70 bg-slate-100/50"
                  style={{ height: `${ROW_HEIGHT}px` }}
                />
              }
            >
              {(item) => (
                <ResultButton
                  href={`/${item().type}/${item().id}`}
                  type={item().type}
                  label={item().label}
                  spaces={wrappingSpaces(item().meta?.contextLabels)}
                  head={headOf(item())}
                  selected={props.showSelected && selected() === row().index}
                  useCount={item().useCount}
                  item={item() as unknown as Record<string, unknown>}
                />
              )}
            </Show>
          </li>
        )}
      </For>
    </ul>
  );
}
