// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { NavExpandedProvider, PageFrame, useNavExpanded } from "./navbar";

const settle = () => new Promise((resolve) => setTimeout(resolve));

test("a page is inset as the console bar is: less with the navigation bar pinned open", async () => {
  const host = document.createElement("div");
  let pin!: (pinned: boolean) => void;
  render(
    () => (
      <NavExpandedProvider>
        {(() => {
          pin = useNavExpanded().setNavPinned;
          return <PageFrame>contents</PageFrame>;
        })()}
      </NavExpandedProvider>
    ),
    host,
  );
  const main = host.querySelector("main")!;
  expect(main.textContent).toBe("contents");
  expect(main.classList.contains("px-20")).toBe(true);
  expect(main.classList.contains("px-8")).toBe(false);
  pin(true);
  await settle();
  expect(main.classList.contains("px-8")).toBe(true);
  expect(main.classList.contains("px-20")).toBe(false);
  pin(false);
});
