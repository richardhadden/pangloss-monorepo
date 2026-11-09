import { Dynamic } from "@solidjs/web";
import { createEffect, createSignal, Show, untrack } from "solid-js";
import type { Component } from "solid-js";
import { useBottomBar } from "./bottomBar";

/**
 * The bar of the clipboard and the stash, whose code is fetched the first time there is something for it to show. It
 * stays once made, so that it can slide away again. Not `lazy`: what is in the clipboard or stash is the browser's, so
 * the server never makes the bar, and a `lazy` first made while the page is being hydrated has to have been made on
 * the server too.
 */
export function ClipboardBarWhenNeeded() {
  const bar = useBottomBar();
  const [loaded, setLoaded] = createSignal<Component>();
  let asked = false;
  createEffect(bar.shown, (shown) => {
    if (!shown || asked || untrack(loaded)) return;
    asked = true;
    void import("./ClipboardBar").then((module) => setLoaded(() => module.default));
  });
  return <Show when={loaded()}>{(component) => <Dynamic component={component()} />}</Show>;
}
