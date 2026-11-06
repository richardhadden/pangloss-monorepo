import {
  getEditView,
  RequireLogin,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createMemo, Errored, Loading, onSettled, refresh, Show } from "solid-js";
import { apiClient } from "../api";
import { revalidateAll } from "../queries";
import { useLeaveGuard } from "../leaving";
import { Page } from "../Page";

// Once the form is on show, scrolls to the document inside it whose id is `id` (the block that has it in
// `data-item-id`), and lights it up for a moment, so the eye finds it
function ScrollToNested(props: { id: string | undefined }) {
  // (read here, not in `onSettled`: reading the address there makes the router's reactive values in a place
  // that may not have them, which the development build stops at)
  const id = props.id;
  onSettled(() => {
    if (!id) return;
    // (after the browser has laid the form out)
    requestAnimationFrame(() => {
      const block = document.querySelector<HTMLElement>(`[data-item-id="${CSS.escape(id)}"]`);
      if (!block) return;
      block.scrollIntoView({ block: "start" });
      block.animate(
        [{ backgroundColor: "rgb(253 230 138 / 0.45)" }, { backgroundColor: "transparent" }],
        { duration: 2000, easing: "ease-out" },
      );
    });
  });
  return null;
}

// Change an item: /Person/<id>/edit (`?show=<id>`: of a document inside it, to scroll to; its own page's
// edit button comes here, as such a document is edited only as a part of the one it is in). Only for someone logged in. The form works on a copy of the
// edit view, and saving sends it back with the version it was loaded at; if someone saved
// meanwhile, the form offers to load the item again (`reload`).
export default function EditItem(props: RouteProps<"/:type/:id/edit">) {
  const ItemForm = useComponent("ItemForm");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const { t } = useTranslations();
  const guardLeaving = useLeaveGuard();
  const item = createMemo(() => getEditView(apiClient(), props.params.type, props.params.id));
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
                  guardLeaving={guardLeaving}
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
              )}
            </Show>
            <Show when={item()}>
              <ScrollToNested id={typeof search.show === "string" ? search.show : undefined} />
            </Show>
          </Loading>
        </Errored>
      </Page>
    </RequireLogin>
  );
}
