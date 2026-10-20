import type { RouteProps } from "@solidjs/router";

// One Document or Entity: /Person/<id>
export default function EntityPage(props: RouteProps<"/:type/:id">) {
  return (
    <main>
      <h1>
        {props.params.type} {props.params.id}
      </h1>
    </main>
  );
}
