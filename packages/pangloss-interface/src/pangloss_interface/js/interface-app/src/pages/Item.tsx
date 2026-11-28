import {
  PageTitle,
  accordingTo,
  ApiError,
  AssertionMark,
  canEdit,
  contextPath,
  Customised,
  CitedByNotice,
  preload,
  getModel,
  groundFacts,
  ItemSections,
  markOf,
  signatureOf,
  spaceFacts,
  ContextFrames,
  Spinner,
  useComponent,
  useModels,
  useModules,
  headOf,
  useTranslations,
  wrappingSpaces,
  PageFrame,
} from "@pangloss/interface-core";
import type {
  ItemMeta,
  ModelDefinitions,
} from "@pangloss/interface-core";
import type { Accessor } from "solid-js";
import type { RouteProps } from "@solidjs/router";
import {
  createEffect,
  createMemo,
  createSignal,
  Errored,
  For,
  Loading,
  onCleanup,
  onSettled,
  Reveal,
  Show,
} from "solid-js";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { isServer } from "@solidjs/web";
import { itemQuery, revalidateAll } from "../queries";
import { ScrollToNested } from "../ScrollToNested";

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
        meta: item.meta,
      });
    },
  );
  // (in the browser only: the server renders a page in passes and discards each, and state is not written there)
  if (!isServer) onCleanup(() => props.onShow(undefined));
  return null;
}

// An entity that was merged into another is read as the one it was merged into (`meta.mergedFrom` has the id asked
// for): the address becomes the survivor's, with `?merged=<the id asked for>`, so that the page can say how the
// reader came to it. (In the browser: the server sends the survivor's page under the address asked for.)
//
// Not before the page the server sent has all come: the new address reads the item again, and a part of the page that
// was still on its way (what refers to the item, a module's section) was then taken over with nothing read, failed,
// and was gone, its nodes left unclaimed, about one time in two. (`_$HY.done`: Solid's own mark that the page's
// stream has ended; a page reached by a link in the browser has it already.)
const pageStillArriving = () => {
  const stream = (globalThis as { _$HY?: { done?: boolean } })._$HY;
  return stream !== undefined && !stream.done;
};

function ToSurvivor(props: { item: Accessor<Awaited<ReturnType<typeof itemQuery>>>; asked: string }) {
  const navigate = useNavigate();
  createEffect(
    () => {
      const item = props.item();
      const from = item.meta.mergedFrom;
      return item.id !== props.asked && Array.isArray(from) && from.includes(props.asked)
        ? `/${item.type}/${encodeURIComponent(item.id)}?merged=${encodeURIComponent(props.asked)}`
        : undefined;
    },
    (href) => {
      if (!href) return;
      let left = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const go = () => {
        if (left) return;
        if (pageStillArriving()) timer = setTimeout(go, 50);
        else navigate(href, { replace: true });
      };
      go();
      return () => {
        left = true;
        clearTimeout(timer);
      };
    },
  );
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
function editHref(shown: Shown | undefined, definitions: ModelDefinitions): string | undefined {
  if (!shown || !written(shown, definitions)) return undefined;
  const head = headOf(shown);
  return head
    ? `/${head.type}/${encodeURIComponent(head.id)}/edit?show=${encodeURIComponent(shown.id)}`
    : `/${shown.type}/${encodeURIComponent(shown.id)}/edit`;
}

// Whether people change the item: not one of a class that something else writes (a derived document), nor a
// document inside one
function written(shown: Shown, definitions: ModelDefinitions): boolean {
  return canEdit(definitions, headOf(shown)?.type ?? shown.type);
}

// The item the console's module actions are for (its own type and id)
function consoleItem(shown: Shown | undefined): { type: string; id: string } | undefined {
  return shown && { type: shown.type, id: shown.id };
}

// Under a head's title: what its ground says of what it holds, in one small line. The mark of a ground that does not
// assert it (a rumour), and whose claim it is where the ground names someone ("According to" and each as a chip, of
// the field its `by` names); nothing for what is asserted by no one, as an entity's own relations are
function HeadGround(props: { item: Record<string, unknown> }) {
  const definitions = useModels();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const type = () => String(props.item.type ?? "");
  const sources = () => accordingTo(definitions, props.item);
  const marked = () =>
    Object.hasOwn(groundFacts(definitions), type()) &&
    markOf(signatureOf([], spaceFacts(definitions), groundFacts(definitions), type())) !== undefined;
  return (
    <Show when={marked() || sources().length > 0}>
      <div class="-mt-3 mb-6 flex flex-wrap items-center gap-3" data-testid="head-ground">
        <AssertionMark path={[]} head={type()} />
        <Show when={sources().length > 0}>
          <span class="shrink-0 text-xs font-semibold text-slate-500 uppercase select-none" data-testid="according-to">
            {t("according_to", "According to")}
          </span>
          <For each={sources()}>
            {(source) => (
              <ReferenceChip
                type={source.type}
                label={source.label ?? source.id}
                href={`/${source.type}/${encodeURIComponent(source.id)}`}
              />
            )}
          </For>
        </Show>
      </div>
    </Show>
  );
}

// One Document or Entity: /Person/<id>
export default function EntityPage(props: RouteProps<"/:type/:id">) {
  const Console = useComponent("Console");
  const ItemContents = useComponent("ItemContents");
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, fieldName } = useTranslations();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  // (`?show=<id>`: a document inside this one, to scroll to)
  const show = () => (typeof search.show === "string" ? search.show : undefined);
  const modules = useModules();
  const item = createMemo(() => {
    // (what the modules add to the page is loaded while the item is read, not once it has come)
    modules.preloadItemPage(props.params.type);
    preload(ItemContents);
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
    meta: ItemMeta;
  }>();
  const definitions = useModels();
  const model = () => getModel(definitions, item().type);
  const ReferenceChip = useComponent("ReferenceChip");
  const head = () => headOf(item());
  // (what the item is inside after its head, round the whole of it; and the field of the head that holds it, or what
  // it is inside)
  const path = () => contextPath(item().meta.path, definitions);
  const headEntry = () => item().meta.path?.[0];
  return (
    <PageFrame>
      {/* (the type is the item's own, which can be a subtype of the one in the address) */}
      <PageTitle type={shown()?.type ?? props.params.type} label={shown()?.label} />
      <Console
        type={shown()?.type ?? props.params.type}
        label={shown()?.label}
        spaces={wrappingSpaces(shown()?.meta)}
        meta={shown()?.meta}
        editHref={editHref(shown(), definitions)}
        item={consoleItem(shown())}
        // (a document inside another is deleted only by taking it out of the one it is in)
        onDeleted={
          shown() && !headOf(shown()!) && written(shown()!, definitions)
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
        <Loading fallback={<p class="pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
          <Track item={item} onShow={setShown} />
          <ToSurvivor item={item} asked={props.params.id} />
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
                {/* (a document inside another: the one it is in) */}
                <Show when={head()}>
                  {(inside) => (
                    <div class="mb-7 flex items-center gap-3 pt-1">
                      <span class="shrink-0 text-xs font-semibold text-slate-500 uppercase select-none">
                        {t("contained_in", "Contained in")}
                      </span>
                      <ReferenceChip
                        type={inside().type}
                        label={item().meta.headNodeLabel ?? inside().id}
                        href={`/${inside().type}/${encodeURIComponent(inside().id)}?show=${encodeURIComponent(item().id)}`}
                      />
                      {/* (in which of its fields: named as a row of the head's own page names it) */}
                      <Show when={headEntry()}>
                        {(entry) => (
                          <span class="min-w-0 text-xs font-semibold text-slate-500 uppercase" data-context-field={entry().field}>
                            {fieldName(entry().type, entry().field)}
                          </span>
                        )}
                      </Show>
                      {/* (what its path says of it, once for the page, where that is not simply that it is so: the
                          bands round the page say in which spaces) */}
                      <AssertionMark path={item().meta.path} />
                    </div>
                  )}
                </Show>
                <ContextFrames path={path()}>
                <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
                  {item().label ?? item().id}
                </h1>
                {/* (a head's ground: the page of a nested item has its one mark in "Contained in" above) */}
                <Show when={!head()}>
                  <HeadGround item={item()} />
                </Show>
                {/* (what refers to the item, and the modules' sections after it, each read apart from the item
                    in a boundary of its own: in the order they are on the page, so that a section does not show
                    before what is above it has, and then move down) */}
                <Reveal>
                  {/* (what the modules have a reader see first: a merge that waits on this entity) */}
                  <ItemSections item={item()} place="before" />
                  {/* (which of it other documents cite as evidence, and which: nothing for one that none cites) */}
                  <Show when={model() !== undefined && model()?.kind !== "Entity"}>
                    <CitedByNotice type={item().type} id={item().id} class="mb-6" />
                  </Show>
                  <ItemContents item={item()} show={show()} />
                  <ItemSections item={item()} />
                </Reveal>
                </ContextFrames>
                <ScrollToNested id={item() ? show() : undefined} />
              </>
            }
          />
        </Loading>
      </Errored>
    </PageFrame>
  );
}
