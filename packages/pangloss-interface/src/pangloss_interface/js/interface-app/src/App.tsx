import {
  ApiProvider,
  ComponentsProvider,
  ModelsProvider,
  NavExpandedProvider,
  createApiClient,
  useComponent,
} from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";
import { Loading } from "solid-js";
import type { ParentProps } from "solid-js";
import { components } from "./components";
import { definitions } from "@generated/models";
import { paths, Router } from "./router";

// (the browser asks the same origin, which passes `/api` on to the API: in development
// the Vite server does, in production whatever is in front of the interface)
const client = createApiClient({ baseUrl: "/api" });

// The frame of every page: the navigation bar, fixed on the left, and the page beside it
function Frame(props: ParentProps) {
  const NavBar = useComponent("NavBar");
  return (
    <>
      <NavBar homeHref={paths()} />
      <div class="min-h-screen pl-10">
        <Loading fallback={<main>Loading…</main>}>{props.children}</Loading>
      </div>
    </>
  );
}

export default function App() {
  return (
    <ComponentsProvider components={components}>
      <ApiProvider client={client}>
        <ModelsProvider definitions={definitions}>
          <NavExpandedProvider>
            <Router>
              {(props) => (
                <>
                  <Title>Pangloss</Title>
                  <Frame>{props.children}</Frame>
                </>
              )}
            </Router>
          </NavExpandedProvider>
        </ModelsProvider>
      </ApiProvider>
    </ComponentsProvider>
  );
}
