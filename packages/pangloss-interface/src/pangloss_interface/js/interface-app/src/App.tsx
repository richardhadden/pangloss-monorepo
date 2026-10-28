import {
  ApiProvider,
  ComponentsProvider,
  ConsoleMountProvider,
  ModelsProvider,
  NavExpandedProvider,
  useComponent,
} from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";
import { Loading } from "solid-js";
import type { ParentProps } from "solid-js";
import { client } from "./api";
import { components } from "./components";
import { definitions } from "@generated/models";
import { paths, Router } from "./router";

// The frame of every page: the navigation bar, fixed on the left, and the page beside it
function Frame(props: ParentProps) {
  const NavBar = useComponent("NavBar");
  const ConsoleBar = useComponent("ConsoleBar");
  return (
    <>
      <NavBar homeHref={paths()} />
      <ConsoleBar />
      <div class="min-h-screen pt-12 pl-12">
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
            </NavExpandedProvider>
        </ModelsProvider>
      </ApiProvider>
    </ComponentsProvider>
  );
}
