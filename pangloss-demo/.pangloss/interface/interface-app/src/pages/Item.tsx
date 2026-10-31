import {
  ApiError,
  Customised,
  getModel,
  useComponent,
  useModels,
  useTranslations,
  wrappingSpaces,
} from "@pangloss/interface-core";
import type { ContextLabel } from "@pangloss/interface-core";
import type { Accessor } from "solid-js";
import type { RouteProps } from "@solidjs/router";
import {
  createEffect,
  createMemo,
  createSignal,
  Errored,
  Loading,
  onCleanup,
  Show,
  untrack,
} from "solid-js";
import { itemQuery } from "../queries";

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
  type: string;
  label: string;
  spaces: ContextLabel[] | null | undefined;
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
        type: item.type,
        label: item.label ?? item.id,
        spaces: item.meta.contextLabels as ContextLabel[] | null | undefined,
      });
    },
  );
  onCleanup(() => props.onShow(undefined));
  return null;
}

// One Document or Entity: /Person/<id>
export default function EntityPage(props: RouteProps<"/:type/:id">) {
  const Console = useComponent("Console");
  const ItemContents = useComponent("ItemContents");
  const ErrorMessage = useComponent("ErrorMessage");
  const item = createMemo(() => itemQuery(props.params.type, props.params.id));
  // (a model may name a page of an interface module for its items: it replaces the rest of this one)
  // What the console says of the item, kept in a signal of its own (set by `Track`, which is inside the error
  // boundary below and so goes with the item's page): the console is outside it, and an item that was there and
  // is not now (a document seen while logged in, not published after logging out) must not leave its label in the bar
  const [shown, setShown] = createSignal<{
    type: string;
    label: string;
    spaces: ContextLabel[] | null | undefined;
  }>();
  const definitions = useModels();
  const model = () => getModel(definitions, item().type);
  return (
    <main class="mx-auto w-full max-w-[100rem] px-6 py-6">
      {/* (the type is the item's own, which can be a subtype of the one in the address) */}
      <Console
        type={shown()?.type ?? props.params.type}
        label={shown()?.label}
        spaces={wrappingSpaces(shown()?.spaces)}
      />
      <Errored
        fallback={(error) => {
          // (the page's own content did not go the way its cleanup would: the bar forgets the item here)
          untrack(() => setShown(undefined));
          return (
            <Show
              when={
                error() instanceof ApiError &&
                (error() as ApiError).status === 404
              }
              fallback={<ErrorMessage error={error()} />}
            >
              <ItemNotFound />
            </Show>
          );
        }}
      >
        <Loading fallback={<p>Loading…</p>}>
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
                <h1 class="mb-6 text-xl font-semibold">
                  {item().label ?? item().id}
                </h1>
                <ItemContents item={item()} />
              </>
            }
          />
        </Loading>
      </Errored>
    </main>
  );
}
