import { RequireLogin, useComponent } from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";

// Make a new Document or Entity: /Person/new. Only for someone logged in: without a login the
// log in dialog opens over the page, and giving up goes home. (The form itself is not built yet.)
export default function NewItem(props: RouteProps<"/:type/new">) {
  const Console = useComponent("Console");
  const navigate = useNavigate();
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <main class="mx-auto w-full max-w-[100rem] px-6 py-6">
        <Console type={props.params.type} label="New" />
      </main>
    </RequireLogin>
  );
}
