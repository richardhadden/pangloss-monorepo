import {
  ApiProvider,
  ComponentsProvider,
  ConsoleMountProvider,
  ModelsProvider,
  ModulesProvider,
  logOut,
  useLoginDialog,
  LoginDialogProvider,
  NavExpandedProvider,
  SessionProvider,
  useComponent,
} from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";
import { revalidate } from "@solidjs/router";
import { createMemo, Loading } from "solid-js";
import type { ParentProps } from "solid-js";
import { apiClient } from "./api";
import { components } from "./components";
import { LoginDialog } from "./LoginDialog";
import { definitions } from "@generated/models";
import { modules } from "@generated/modules";
import { sessionQuery } from "./queries";
import { paths, Router } from "./router";

// The frame of every page: the navigation bar, fixed on the left, and the page beside it
function Frame(props: ParentProps) {
  const NavBar = useComponent("NavBar");
  const ConsoleBar = useComponent("ConsoleBar");
  const { openLogin } = useLoginDialog();
  // Who is logged in (an async memo: what reads `user()` waits for it, inside a `Loading`).
  // The server holds back the first part of the page until it is known, so the bar is not
  // sent as "not logged in" and then changed.
  const user = createMemo(() => sessionQuery(), { deferStream: true });
  async function logOutHere() {
    await logOut(apiClient());
    revalidate(sessionQuery.key);
  }
  return (
    <SessionProvider user={user}>
      {/* (the bar reads the user, so it waits for it: until then, one with no one logged in) */}
      <Loading fallback={<NavBar homeHref={paths()} onLogin={openLogin} />}>
        <NavBar
          homeHref={paths()}
          user={user()?.username}
          onLogin={openLogin}
          onLogout={logOutHere}
        />
      </Loading>
      <ConsoleBar />
      <div class="min-h-screen pt-12 pl-12">
        <Loading fallback={<main>Loading…</main>}>{props.children}</Loading>
      </div>
      <LoginDialog />
    </SessionProvider>
  );
}

export default function App() {
  return (
    <ComponentsProvider components={components}>
      <ApiProvider client={apiClient()}>
        <ModelsProvider definitions={definitions}>
          <ModulesProvider modules={modules}>
            <NavExpandedProvider>
              <LoginDialogProvider>
                <ConsoleMountProvider>
                  <Router>
                    {(props) => (
                      <>
                        <Title>Pangloss</Title>
                        <Frame>{props.children}</Frame>
                      </>
                    )}
                  </Router>
                </ConsoleMountProvider>
              </LoginDialogProvider>
            </NavExpandedProvider>
          </ModulesProvider>
        </ModelsProvider>
      </ApiProvider>
    </ComponentsProvider>
  );
}
