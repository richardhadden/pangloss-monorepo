// In its own module so that anything that needs the router (the App, and later the
// server) shares one
import { pageRoutes } from "virtual:file-routes";
import { createRouter, intentPreload } from "@solidjs/router";
import { fileRoutes } from "@solidjs/router/fs";

export const Router = createRouter({
  routes: fileRoutes(pageRoutes),
  preloadLinks: intentPreload(),
});

export const { paths } = Router;
