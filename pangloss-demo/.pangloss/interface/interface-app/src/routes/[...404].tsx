import { Title } from "@solidjs/meta";
import type { RouteDefinition } from "@solidjs/router";
import { httpStatus } from "@solidjs/web";

// (the status of the response is set while it is rendered on the server)
export const route = {
  preload: () => httpStatus(404),
} satisfies RouteDefinition;

export default function NotFound() {
  return (
    <main>
      <Title>Not found - Pangloss</Title>
      <h1>Page not found</h1>
    </main>
  );
}
