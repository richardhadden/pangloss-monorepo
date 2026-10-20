import {
  ApiProvider,
  ComponentsProvider,
  ModelsProvider,
  createApiClient,
} from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";
import { Loading } from "solid-js";
import { components } from "./components";
import { definitions } from "@generated/models";
import { paths, Router } from "./router";

// (the browser asks the same origin, which passes `/api` on to the API: in development
// the Vite server does, in production whatever is in front of the interface)
const client = createApiClient({ baseUrl: "/api" });

export default function App() {
  return (
    <ComponentsProvider components={components}>
      <ApiProvider client={client}>
        <ModelsProvider definitions={definitions}>
          <Router>
            {(props) => (
              <>
                <Title>Pangloss</Title>
                <nav>
                  <a href={paths()}>Home</a>
                </nav>
                <Loading fallback={<main>Loading…</main>}>{props.children}</Loading>
              </>
            )}
          </Router>
        </ModelsProvider>
      </ApiProvider>
    </ComponentsProvider>
  );
}
