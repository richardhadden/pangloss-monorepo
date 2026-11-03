import {
  blankItem,
  canCreate,
  getModel,
  RequireLogin,
  useComponent,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { Show } from "solid-js";
import { revalidateAll } from "../queries";
import { Page } from "../Page";

// Make a new Document or Entity: /Person/new. Only for someone logged in: without a login the
// log in dialog opens over the page, and giving up goes home. Saving goes to the new item.
// A type that cannot be made on its own (abstract, or `create_directly=False`) says so instead.
export default function NewItem(props: RouteProps<"/:type/new">) {
  const definitions = useModels();
  const model = () => getModel(definitions, props.params.type);
  return (
    <Show
      when={model() === undefined || canCreate(model()!)}
      fallback={<CannotCreate type={props.params.type} abstract={model()!.abstract} />}
    >
      <NewItemForm {...props} />
    </Show>
  );
}

function NewItemForm(props: RouteProps<"/:type/new">) {
  const ItemForm = useComponent("ItemForm");
  const definitions = useModels();
  const navigate = useNavigate();
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <Page>
        <ItemForm
          type={props.params.type}
          initial={blankItem(definitions, props.params.type)}
          onSaved={(saved) => {
            void revalidateAll();
            navigate(`/${saved.type}/${encodeURIComponent(saved.id)}`);
          }}
          onCancel={() => navigate(`/${props.params.type}`)}
        />
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
