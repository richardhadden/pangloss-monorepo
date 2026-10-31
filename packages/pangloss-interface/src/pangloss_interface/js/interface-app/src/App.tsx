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
  useNavExpanded,
  TranslationsProvider,
  SessionProvider,
  useComponent,
} from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";
import { createMemo, Loading } from "solid-js";
import type { ParentProps } from "solid-js";
import { apiClient } from "./api";
import { components } from "./components";
import { LoginDialog } from "./LoginDialog";
import { definitions } from "@generated/models";
import { modules } from "@generated/modules";
import { revalidateAll, sessionQuery } from "./queries";
import { paths, Router } from "./router";
import { loadTranslations } from "./translations";

// The frame of every page: the navigation bar, fixed on the left, and the page beside it
function Frame(props: ParentProps) {
  const NavBar = useComponent("NavBar");
  const ConsoleBar = useComponent("ConsoleBar");
  const { openLogin } = useLoginDialog();
  const { navPinned } = useNavExpanded();
  // Who is logged in (an async memo: what reads `user()` waits for it, inside a `Loading`).
  // The server holds back the first part of the page until it is known, so the bar is not
  // sent as "not logged in" and then changed.
  const user = createMemo(() => sessionQuery(), { deferStream: true });
  async function logOutHere() {
    await logOut(apiClient());
    revalidateAll();
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
      <div
        class={[
          "min-h-screen pt-12 transition-[padding] duration-150",
          { "pl-72": navPinned(), "pl-12": !navPinned() },
        ]}
      >
        <Loading fallback={<main>Loading…</main>}>{props.children}</Loading>
      </div>
      <LoginDialog />
    </SessionProvider>
  );
}

export default function App() {
  // (the default language is read before the page is sent; the others, when someone chooses them)
  const initialTranslations = createMemo(() => loadTranslations(), {
    deferStream: true,
  });
  return (
    <ComponentsProvider components={components}>
      <ApiProvider client={apiClient()}>
        <ModelsProvider definitions={definitions}>
          <ModulesProvider modules={modules}>
            <Loading fallback={null}>
              <TranslationsProvider
                initial={initialTranslations()}
                load={loadTranslations}
              >
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
              </TranslationsProvider>
            </Loading>
          </ModulesProvider>
        </ModelsProvider>
      </ApiProvider>
    </ComponentsProvider>
  );
}
