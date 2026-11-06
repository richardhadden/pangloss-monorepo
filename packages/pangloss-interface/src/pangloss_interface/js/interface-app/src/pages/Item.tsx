import {
  ApiError,
  Customised,
  getModel,
  ItemSections,
  useComponent,
  useModels,
  useModules,
  headOf,
  useTranslations,
  wrappingSpaces,
} from "@pangloss/interface-core";
import type {
  ContextLabel,
  ItemMeta,
} from "@pangloss/interface-core";
import type { Accessor } from "solid-js";
import type { RouteProps } from "@solidjs/router";
import {
  createEffect,
  createMemo,
  createSignal,
  Errored,
  Loading,
  onCleanup,
  onSettled,
  Show,
} from "solid-js";
import { useNavigate } from "@solidjs/router";
import { isServer } from "@solidjs/web";
import { itemQuery, revalidateAll } from "../queries";
import { Page } from "../Page";

// An item that is not there for this reader: it does not exist, or (as an unpublished document is to
// someone who is not logged in) they may not see it. The API says which, but the page does not tell.
function ItemNotFound() {
  const { t } = useTranslations();
  return (
    <>
      <h1 class="mb-3 text-xl font-semibold">
        {t("page_not_found", "Page not found")}
      </h1>
      <p role="alert">
        {t(
          "item_not_found",
          "There is nothing here. It may not exist, or you may need to log in to see it.",
        )}
      </p>
    </>
  );
}

interface Shown {
  id: string;
  type: string;
  label: string;
  spaces: ContextLabel[] | null | undefined;
  meta: ItemMeta;
}

// Tells the page what the console is to say of the item, for as long as the item is on show
function Track(props: {
  item: Accessor<Awaited<ReturnType<typeof itemQuery>>>;
  onShow: (shown: Shown | undefined) => void;
}) {
  createEffect(
    () => props.item(),
    (item) => {
      // (braces: what an effect returns is taken to be its cleanup)
      props.onShow({
        id: item.id,
        type: item.type,
        label: item.label ?? item.id,
        spaces: item.meta.contextLabels as ContextLabel[] | null | undefined,
        meta: item.meta,
      });
    },
  );
  // (in the browser only: the server renders a page in passes and discards each, and state is not written there)
  if (!isServer) onCleanup(() => props.onShow(undefined));
  return null;
}

// Tells the page that no item is on show, once the error that is in its place is (not while it is
// rendered: state is not written then)
function Forget(props: { onShow: (shown: undefined) => void }) {
  onSettled(() => props.onShow(undefined));
  return null;
}

// Where the edit button goes: the item's own form, or, for a document inside another (which is edited only
// as a part of it), the form of the one it is in, scrolled to it
function editHref(shown: Shown | undefined): string | undefined {
  if (!shown) return undefined;
  const head = headOf(shown);
  return head
    ? `/${head.type}/${encodeURIComponent(head.id)}/edit?show=${encodeURIComponent(shown.id)}`
    : `/${shown.type}/${encodeURIComponent(shown.id)}/edit`;
}

// The item the console's module actions are for (its own type and id)
function consoleItem(shown: Shown | undefined): { type: string; id: string } | undefined {
  return shown && { type: shown.type, id: shown.id };
}

// One Document or Entity: /Person/<id>
export default function EntityPage(props: RouteProps<"/:type/:id">) {
  const Console = useComponent("Console");
  const ItemContents = useComponent("ItemContents");
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  const navigate = useNavigate();
  const modules = useModules();
  const item = createMemo(() => {
    // (what the modules add to the page is loaded while the item is read, not once it has come)
    modules.preloadItemPage(props.params.type);
    return itemQuery(props.params.type, props.params.id);
  });
  // (a model may name a page of an interface module for its items: it replaces the rest of this one)
  // What the console says of the item, kept in a signal of its own (set by `Track`, which is inside the error
  // boundary below and so goes with the item's page): the console is outside it, and an item that was there and
  // is not now (a document seen while logged in, not published after logging out) must not leave its label in the bar
  const [shown, setShown] = createSignal<{
    id: string;
    type: string;
    label: string;
    spaces: ContextLabel[] | null | undefined;
    meta: ItemMeta;
  }>();
  const definitions = useModels();
  const model = () => getModel(definitions, item().type);
  return (
    <Page>
      {/* (the type is the item's own, which can be a subtype of the one in the address) */}
      <Console
        type={shown()?.type ?? props.params.type}
        label={shown()?.label}
        spaces={wrappingSpaces(shown()?.spaces)}
        meta={shown()?.meta}
        editHref={editHref(shown())}
        item={consoleItem(shown())}
        // (a document inside another is deleted only by taking it out of the one it is in)
        onDeleted={
          shown() && !headOf(shown()!)
            ? () => {
                const type = shown()!.type;
                void revalidateAll();
                navigate(`/${type}`, { replace: true });
              }
            : undefined
        }
        page="item"
      />
      <Errored
        fallback={(error) => (
          <>
            {/* (the page's own content did not go the way its cleanup would: the bar forgets the item here) */}
            <Forget onShow={setShown} />
            <Show
              when={
                error() instanceof ApiError &&
                (error() as ApiError).status === 404
              }
              fallback={<ErrorMessage error={error()} />}
            >
              <ItemNotFound />
            </Show>
          </>
        )}
      >
        <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
          <Track item={item} onShow={setShown} />
          <Customised
            slot="itemPage"
            type={item().type}
            skip={model() === undefined}
            props={{
              type: item().type,
              id: props.params.id,
              item: item(),
              model: model()!,
            }}
            fallback={
              <>
                <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
                  {item().label ?? item().id}
                </h1>
                <ItemContents item={item()} />
                <ItemSections item={item()} />
              </>
            }
          />
        </Loading>
      </Errored>
    </Page>
  );
}
