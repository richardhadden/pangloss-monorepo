// The routes of the application, in code. Each page is `lazy`, so it is a chunk of its own,
// fetched when it is needed, or sooner, when a link to it is hovered, focused or touched
// (`preloadLinks` in router.ts). A route's `preload` starts what its page reads at the same
// time; it only calls the query (`void`), and the page reads the same query through a memo, so
// the two share one request. (`/:type/new` is static, so it comes before `/:type/:id`.)
import { defineRoute, defineRoutes } from "@solidjs/router";
import { httpStatus } from "@solidjs/web";
import { lazy } from "solid-js";
import { orderModules } from "@pangloss/interface-core";
import { modules } from "@generated/modules";
import { itemQuery, listQuery, searchOf } from "./queries";

// The pages of the interface modules of the installed apps: before `/:type`, which would take their addresses for a type
// (a module that has none adds none)
const moduleRoutes = orderModules(modules).flatMap((module) =>
  (module.routes ?? []).map((route) =>
    defineRoute({
      path: route.path,
      component: lazy(module.components[route.component]!),
      preload: route.preload as never,
    }),
  ),
);

export const routes = defineRoutes([
  defineRoute({ path: "/", component: lazy(() => import("./pages/Home")) }),
  ...moduleRoutes,
  defineRoute({
    path: "/:type",
    component: lazy(() => import("./pages/List")),
    preload: ({ params, location }) => {
      const { q, deep } = searchOf(location.query);
      void listQuery(params.type, q, deep, 1);
    },
  }),
  defineRoute({ path: "/:type/new", component: lazy(() => import("./pages/New")) }),
  defineRoute({
    path: "/:type/:id",
    component: lazy(() => import("./pages/Item")),
    preload: ({ params }) => void itemQuery(params.type, params.id),
  }),
  defineRoute({
    path: "*404",
    component: lazy(() => import("./pages/NotFound")),
    // (the status of the response is set while it is rendered on the server)
    preload: () => httpStatus(404),
  }),
])
