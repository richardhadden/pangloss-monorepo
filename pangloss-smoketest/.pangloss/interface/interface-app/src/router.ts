// In its own module so that anything that needs the router (the App, and later the
// server) shares one
import { createRouter, intentPreload } from "@solidjs/router";
import { routes } from "./routes";

export const Router = createRouter({
  routes,
  // a link that is hovered, focused or touched starts the page's code and its `preload`
  preloadLinks: intentPreload(),
});

export const { paths } = Router;
