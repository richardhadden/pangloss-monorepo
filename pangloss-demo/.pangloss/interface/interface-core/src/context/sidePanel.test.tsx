// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal, flush, Show } from "solid-js";
import { afterEach, expect, test } from "vitest";
import { SidePanelProvider, useSidePanel } from "./sidePanel";
import type { SidePanel } from "./sidePanel";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  dispose = undefined;
  document.body.innerHTML = "";
});

function Panel(props: { name: string; onPanel: (panel: SidePanel) => void }) {
  const panel = useSidePanel(props.name);
  props.onPanel(panel);
  return <span data-testid={props.name} data-open={panel.open() ? "true" : "false"} />;
}

const state = (name: string) => document.querySelector(`[data-testid="${name}"]`)?.getAttribute("data-open");

test("opening one panel closes the other, and closing one leaves the other closed", () => {
  const panels: Record<string, SidePanel> = {};
  dispose = render(
    () => (
      <SidePanelProvider>
        <Panel name="review" onPanel={(p) => (panels.review = p)} />
        <Panel name="history" onPanel={(p) => (panels.history = p)} />
      </SidePanelProvider>
    ),
    document.body,
  );
  panels.review!.setOpen(true);
  flush();
  expect([state("review"), state("history")]).toEqual(["true", "false"]);

  panels.history!.setOpen((was) => !was);
  flush();
  expect([state("review"), state("history")]).toEqual(["false", "true"]);

  // (closing one that is not open changes nothing)
  panels.review!.setOpen(false);
  flush();
  expect(state("history")).toBe("true");

  panels.history!.setOpen((was) => !was);
  flush();
  expect([state("review"), state("history")]).toEqual(["false", "false"]);
});

test("a panel on the next page is closed, though the one before was open", () => {
  const panels: SidePanel[] = [];
  const [page, setPage] = createSignal(1);
  dispose = render(
    () => (
      <SidePanelProvider>
        <Show when={page() === 1} fallback={<Panel name="history" onPanel={(p) => panels.push(p)} />}>
          <Panel name="history" onPanel={(p) => panels.push(p)} />
        </Show>
      </SidePanelProvider>
    ),
    document.body,
  );
  panels[0]!.setOpen(true);
  flush();
  expect(state("history")).toBe("true");
  setPage(2);
  flush();
  expect(state("history")).toBe("false");
});

test("without a provider, a panel opens and closes on its own", () => {
  let panel: SidePanel | undefined;
  dispose = render(() => <Panel name="alone" onPanel={(p) => (panel = p)} />, document.body);
  panel!.setOpen(true);
  flush();
  expect(state("alone")).toBe("true");
  panel!.setOpen(false);
  flush();
  expect(state("alone")).toBe("false");
});
