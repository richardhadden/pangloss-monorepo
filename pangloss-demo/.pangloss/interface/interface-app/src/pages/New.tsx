import {
  PageTitle,
  blankItem,
  canCreate,
  getModel,
  RequireLogin,
  useComponent,
  useModels,
  useStash,
  useTranslations,
  withCurrentReferences,
  Spinner,
} from "@pangloss/interface-core";
import type { FormData } from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createEffect, createSignal, Show, untrack } from "solid-js";
import { apiClient } from "../api";
import { useLeaveGuard } from "../leaving";
import { revalidateAll } from "../queries";
import { Page } from "../Page";

// What the form starts with: a blank item, or one taken from the stash (`key`), with the entities it refers to
// brought up to date (`gone`: those no longer there, taken out)
interface Start {
  key?: string;
  value?: FormData;
  gone: { type: string; id: string; label?: string }[];
}

// Make a new Document or Entity: /Person/new. Only for someone logged in: without a login the
// log in dialog opens over the page, and giving up goes home. Saving goes to the new item.
// A type that cannot be made on its own (abstract, or `create_directly=False`) says so instead.
// `?stash=<key>`: go on with a stashed item (stashing one goes to the list of the type, where the stash is shown).
export default function NewItem(props: RouteProps<"/:type/new">) {
  const definitions = useModels();
  const model = () => getModel(definitions, props.params.type);
  const { t } = useTranslations();
  return (
    <>
      <PageTitle action={t("title_new", "New")} type={props.params.type} />
      <Show
        when={model() === undefined || canCreate(model()!)}
        fallback={<CannotCreate type={props.params.type} abstract={model()!.abstract} />}
      >
        <NewItemForm {...props} />
      </Show>
    </>
  );
}

function NewItemForm(props: RouteProps<"/:type/new">) {
  const ItemForm = useComponent("ItemForm");
  const definitions = useModels();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const { t } = useTranslations();
  const stash = useStash();
  const guardLeaving = useLeaveGuard();
  const stashKey = () => (typeof search.stash === "string" && search.stash !== "" ? search.stash : undefined);
  // (the stash is the browser's: what is in it is read once settled, so the server renders "Loading" for it)
  const [start, setStart] = createSignal<Start | undefined>(untrack(() => (stashKey() ? undefined : { gone: [] })));
  // (the stashed items of this type are shown beside the clipboard, while the page is about it)
  createEffect(
    () => props.params.type,
    (type) => stash?.showFor(type),
  );
  // (a blank form stays the one it is: it is not made again when nothing has changed)
  const blank = () => {
    const now = untrack(start);
    if (!now || now.key !== undefined) setStart({ gone: [] });
  };
  createEffect(stashKey, (key) => {
    const entry = key ? untrack(() => stash?.get(key)) : undefined;
    if (!key || !entry) {
      blank();
      return;
    }
    setStart(undefined);
    let current = true;
    withCurrentReferences(apiClient(), definitions, entry.value).then(
      (refreshed) => current && setStart({ key, value: refreshed.value, gone: refreshed.gone }),
      // (the API cannot be asked: the item as it was stashed; saving it will say what is wrong)
      () => current && setStart({ key, value: entry.value, gone: [] }),
    );
    return () => {
      current = false;
    };
  });
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <Page>
        <Show when={start()} keyed fallback={<p class="pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
          {(begin) => (
            <ItemForm
              type={props.params.type}
              initial={begin.value ?? blankItem(definitions, props.params.type)}
              baseline={begin.value ? blankItem(definitions, props.params.type) : undefined}
              stashed={begin.key ? { key: begin.key, gone: begin.gone } : undefined}
              guardLeaving={guardLeaving}
              onSaved={(saved) => {
                void revalidateAll();
                navigate(`/${saved.type}/${encodeURIComponent(saved.id)}`);
              }}
              onCancel={() => navigate(`/${props.params.type}`)}
              onStashed={() => navigate(`/${props.params.type}`)}
            />
          )}
        </Show>
      </Page>
    </RequireLogin>
  );
}

function CannotCreate(props: { type: string; abstract: boolean }) {
  const Console = useComponent("Console");
  const { t, modelName } = useTranslations();
  return (
    <Page>
      <Console type={props.type} list />
      <p data-testid="cannot-create">
        {props.abstract
          ? t(
              "cannot_create_abstract",
              "{type} is an abstract type: a new one is made as one of its types.",
              { type: modelName(props.type) },
            )
          : t(
              "cannot_create_directly",
              "{type} cannot be made on its own, only as part of another document.",
              { type: modelName(props.type) },
            )}
      </p>
    </Page>
  );
}
