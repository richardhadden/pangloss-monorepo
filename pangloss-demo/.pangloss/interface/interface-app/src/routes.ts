// The routes of the application, in code. Each page is `lazy`, so it is a chunk of its own,
// fetched when it is needed, or sooner, when a link to it is hovered, focused or touched
// (`preloadLinks` in router.ts). A route's `preload` starts what its page reads at the same
// time; it only calls the query (`void`), and the page reads the same query through a memo, so
// the two share one request. (`/:type/new` is static, so it comes before `/:type/:id`.)
import { defineRoute, defineRoutes } from "@solidjs/router";
import { httpStatus } from "@solidjs/web";
import { lazy } from "solid-js";
import { orderModules } from "@pangloss/interface-core";
import type { PageLoader } from "@pangloss/interface-core";
import { definitions } from "@generated/models";
import { modules } from "@generated/modules";
import { pageComponent, projectHome, projectPages } from "./projectPages";
import { itemQuery, listQuery, pageOf, searchOf, startOf, requestOf, usesOf } from "./queries";

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

const defaultHome = () => import("./pages/Home");

export const routes = defineRoutes([
  defineRoute({ path: "/", component: pageComponent(projectHome ?? (defaultHome as PageLoader)) }),
  // (a project's own pages, before `/:type`, which would take their addresses for a type)
  ...projectPages.map((page) => defineRoute({ path: `/${page.slug}`, component: pageComponent(page.load, page.slug) })),
  ...moduleRoutes,
  defineRoute({
    path: "/:type",
    component: lazy(() => import("./pages/List")),
    preload: ({ params, location }) => {
      const { q, deep, form, all } = searchOf(location.query);
      const request = requestOf(params.type, form, q);
      void listQuery(params.type, q, deep && !request, request, pageOf(startOf(location.query)), usesOf(definitions, params.type, all));
    },
  }),
  defineRoute({ path: "/:type/new", component: lazy(() => import("./pages/New")) }),
  defineRoute({ path: "/:type/:id/edit", component: lazy(() => import("./pages/Edit")) }),
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
