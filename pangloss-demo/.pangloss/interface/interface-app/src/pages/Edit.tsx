import {
  canEdit,
  getEditView,
  PageTitle,
  preload,
  RequireLogin,
  useComponent,
  useModels,
  useTranslations,
  Spinner,
  PageFrame,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, Loading, refresh, Show } from "solid-js";
import { apiClient } from "../api";
import { revalidateAll } from "../queries";
import { useLeaveGuard } from "../leaving";
import { ScrollToNested } from "../ScrollToNested";

// Change an item: /Person/<id>/edit (`?show=<id>`: of a document inside it, to scroll to; its own page's
// edit button comes here, as such a document is edited only as a part of the one it is in). Only for someone logged in. The form works on a copy of the
// edit view, and saving sends it back with the version it was loaded at; if someone saved
// meanwhile, the form offers to load the item again (`reload`).
export default function EditItem(props: RouteProps<"/:type/:id/edit">) {
  const ItemForm = useComponent("ItemForm");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const { t, modelName } = useTranslations();
  const guardLeaving = useLeaveGuard();
  const item = createMemo(() => {
    // (the form's code is loaded while the item is read)
    preload(ItemForm);
    return getEditView(apiClient(), props.params.type, props.params.id);
  });
  const definitions = useModels();
  const Console = useComponent("Console");
  return (
    <Show
      when={canEdit(definitions, props.params.type)}
      fallback={
        // (a class that something else writes, a derived document: there is nothing to edit)
        <PageFrame>
          <PageTitle action={t("title_edit", "Edit")} type={props.params.type} />
          <Console type={props.params.type} list />
          <p data-testid="cannot-edit">
            {t("cannot_edit_not_written", "A {type} is not edited by hand: it is made and kept by what derives it.", {
              type: modelName(props.params.type),
            })}
          </p>
        </PageFrame>
      }
    >
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle action={t("title_edit", "Edit")} type={props.params.type} />
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p class="pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
            {/* (the form starts from a copy of the item, so it is made once the item is here, and again for a new one) */}
            <Show when={item()} keyed>
              {(loaded) => (
                <>
                <PageTitle action={t("title_edit", "Edit")} type={loaded.type} label={loaded.label} />
                <ItemForm
                  type={loaded.type}
                  initial={loaded}
                  version={loaded.meta.version}
                  meta={loaded.meta}
                  guardLeaving={guardLeaving}
                  show={typeof search.show === "string" ? search.show : undefined}
                  onSaved={(saved) => {
                    void revalidateAll();
                    navigate(`/${saved.type}/${encodeURIComponent(saved.id)}`);
                  }}
                  onCancel={() => navigate(`/${loaded.type}/${encodeURIComponent(loaded.id)}`)}
                  onDeleted={() => {
                    void revalidateAll();
                    navigate(`/${loaded.type}`, { replace: true });
                  }}
                  onReload={() => void refresh(item)}
                />
                </>
              )}
            </Show>
            <Show when={item()}>
              <ScrollToNested id={typeof search.show === "string" ? search.show : undefined} />
            </Show>
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
    </Show>
  );
}
