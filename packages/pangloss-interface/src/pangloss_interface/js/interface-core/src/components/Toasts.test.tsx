// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import { TOAST_MS, ToastsProvider, useToasts } from "../context";
import { Toasts } from "./Toasts";

afterEach(() => vi.useRealTimers());

function mount() {
  vi.useFakeTimers();
  const host = document.createElement("div");
  let show!: (message: string, tone?: "success" | "error") => void;
  render(
    () => (
      <ToastsProvider>
        {(() => {
          show = useToasts()!.show;
          return <Toasts />;
        })()}
      </ToastsProvider>
    ),
    host,
  );
  return { host, show: (message: string) => show(message) };
}

const flush = () => vi.advanceTimersByTimeAsync(0);

test("a toast is shown, and goes after a few seconds", async () => {
  const { host, show } = mount();
  show("Person “Alcuin” saved");
  await flush();
  expect(host.textContent).toContain("Person “Alcuin” saved");
  await vi.advanceTimersByTimeAsync(TOAST_MS + 10);
  expect(host.textContent).not.toContain("Alcuin");
});

test("clicking a toast closes it", async () => {
  const { host, show } = mount();
  show("Saved");
  await flush();
  host.querySelector("button")!.click();
  await flush();
  expect(host.querySelector("button")).toBeNull();
});
