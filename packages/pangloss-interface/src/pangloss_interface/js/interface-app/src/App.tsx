import { useNavigate } from "@solidjs/router";
import {
  ApiProvider,
  ClipboardProvider,
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
  SidePanelProvider,
  StashProvider,
  ToastsProvider,
  TypeInfoPopup,
  useBottomBar,
  useComponent,
  useTranslations,
  Spinner,
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
  const ClipboardBar = useComponent("ClipboardBar");
  const Toasts = useComponent("Toasts");
  const navigate = useNavigate();
  const { openLogin } = useLoginDialog();
  const { navPinned } = useNavExpanded();
  const { t } = useTranslations();
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
      {/* (each user has their own clipboard) */}
      <ClipboardProvider owner={() => user()?.username}>
       <StashProvider owner={() => user()?.username}>
        {/* (the frame outlives the pages, so a toast stays when a save goes to another page) */}
        <ToastsProvider>
          {/* (the bar reads the user, so it waits for it: until then, one with no one logged in) */}
          <Loading fallback={<NavBar homeHref={paths()} onLogin={openLogin} />}>
            <NavBar
              homeHref={paths()}
              user={user()?.username}
              onLogin={openLogin}
              onLogout={logOutHere}
              onNavigate={(href) => navigate(href)}
            />
          </Loading>
          <ConsoleBar />
          <Padded navPinned={navPinned()}>
            <Loading fallback={<main class="p-6 text-slate-500"><Spinner class="size-5" /></main>}>{props.children}</Loading>
          </Padded>
          <ClipboardBar />
          <Toasts />
          <TypeInfoPopup />
          <LoginDialog />
        </ToastsProvider>
       </StashProvider>
      </ClipboardProvider>
    </SessionProvider>
  );
}

// The page beside the nav bar, clear of the console bar, and of the bar of the clipboard and stash when it is showing
function Padded(props: ParentProps<{ navPinned: boolean }>) {
  const bottomBar = useBottomBar();
  const barShown = bottomBar.shown;
  return (
    <div
      class={[
        "min-h-screen pt-12 transition-[padding] duration-150",
        {
          "pl-72": props.navPinned,
          "pl-12": !props.navPinned,
          "pb-48": barShown() && !bottomBar.collapsed(),
          "pb-12": barShown() && bottomBar.collapsed(),
        },
      ]}
    >
      {props.children}
    </div>
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
                      {/* (one panel on the right at a time: review, history, ...) */}
                      <SidePanelProvider>
                        <Router>
                          {(props) => (
                            <>
                              <Title>Pangloss</Title>
                              <Frame>{props.children}</Frame>
                            </>
                          )}
                        </Router>
                      </SidePanelProvider>
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
