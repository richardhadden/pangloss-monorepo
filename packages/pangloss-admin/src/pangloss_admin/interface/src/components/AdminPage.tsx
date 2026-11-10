import { NotFound, PageTitle, RequireLogin, useComponent, useCurrentUser, useModules, useTranslations, PageFrame } from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import { createMemo, For, Loading, Show } from "solid-js";
import type { ParentProps } from "solid-js";

function AdminContents() {
  const Console = useComponent("Console");
  const { t } = useTranslations();
  const sections = useModules().slot("admin");
  return (
    <PageFrame>
      <div data-testid="admin-page">
      <PageTitle section={t("admin_title", "Admin")} />
      <Console type={t("admin_title", "Admin")} />
      <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">{t("admin_title", "Admin")}</h1>
      {/* (the gap is here, as the order of the sections is the order of the modules) */}
      <div class="space-y-10">
        <For each={sections}>
          {(Section) => (
            <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
              <Section />
            </Loading>
          )}
        </For>
      </div>
      </div>
    </PageFrame>
  );
}

/**
 * `/admin`. Someone not logged in gets the login dialog, so that an admin can come here by the address alone; someone
 * logged in who is not an admin is told there is nothing here. (The API refuses them in any case: this is what is shown.)
 */
export default function AdminPage() {
  const navigate = useNavigate();
  return (
    <RequireLogin onCancel={() => navigate("/")}>
      <AdminOrNothing>
        <AdminContents />
      </AdminOrNothing>
    </RequireLogin>
  );
}

function AdminOrNothing(props: ParentProps) {
  const isAdmin = createMemo(() => useCurrentUser()?.admin === true);
  return (
    <Show when={isAdmin()} fallback={<NotFound />}>
      {props.children}
    </Show>
  );
}
