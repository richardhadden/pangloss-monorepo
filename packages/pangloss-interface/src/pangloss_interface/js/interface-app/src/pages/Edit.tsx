import {
  getEditView,
  RequireLogin,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, createSignal, Errored, Loading, Show } from "solid-js";
import { apiClient } from "../api";
import { revalidateAll } from "../queries";
import { Page } from "../Page";

// Change an item: /Person/<id>/edit. Only for someone logged in. The form works on a copy of the
// edit view, and saving sends it back with the version it was loaded at; if someone saved
// meanwhile, the form offers to load the item again (`reload`).
export default function EditItem(props: RouteProps<"/:type/:id/edit">) {
  const ItemForm = useComponent("ItemForm");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  const [reload, setReload] = createSignal(0);
  const item = createMemo(() => {
    reload();
    return getEditView(apiClient(), props.params.type, props.params.id);
  });
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <Page>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            {/* (the form starts from a copy of the item, so it is made once the item is here, and again for a new one) */}
            <Show when={item()} keyed>
              {(loaded) => (
                <ItemForm
                  type={loaded.type}
                  initial={loaded}
                  version={loaded.meta.version}
                  meta={loaded.meta}
                  onSaved={(saved) => {
                    void revalidateAll();
                    navigate(`/${saved.type}/${encodeURIComponent(saved.id)}`);
                  }}
                  onCancel={() => navigate(`/${loaded.type}/${encodeURIComponent(loaded.id)}`)}
                  onReload={() => setReload(reload() + 1)}
                />
              )}
            </Show>
          </Loading>
        </Errored>
      </Page>
    </RequireLogin>
  );
}
