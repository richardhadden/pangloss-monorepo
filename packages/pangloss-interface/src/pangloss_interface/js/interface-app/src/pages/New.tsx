import { blankItem, RequireLogin, useComponent, useModels } from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { revalidateAll } from "../queries";
import { Page } from "../Page";

// Make a new Document or Entity: /Person/new. Only for someone logged in: without a login the
// log in dialog opens over the page, and giving up goes home. Saving goes to the new item.
export default function NewItem(props: RouteProps<"/:type/new">) {
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
