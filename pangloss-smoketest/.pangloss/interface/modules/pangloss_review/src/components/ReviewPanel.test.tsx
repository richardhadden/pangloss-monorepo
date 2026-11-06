// @vitest-environment happy-dom
import { ModelsProvider } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { Comment } from "../api";
import type { ReviewView } from "../state";
import { ReviewPanel } from "./ReviewPanel";
import type { ReviewPanelProps } from "./ReviewPanel";

const comment = (id: string, username: string, at: string, more: Partial<Comment> = {}): Comment => ({
  id,
  username,
  at,
  text: `text of ${id}`,
  resolved: false,
  ...more,
});

const PART = "01a1a11c-8979-71fc-8c48-000000000002";
const DEFINITIONS: ModelDefinitions = {
  models: { Statement: { name: "Statement", kind: "Document", interfaceMeta: null } as unknown as ModelDefinition },
  enums: {},
};

const VIEW: ReviewView = {
  id: "d1",
  state: "ready",
  status: "errors_found",
  published: false,
  reviewedBy: "bob",
  reviewedAt: "2026-11-01T10:00:00Z",
  openComments: 2,
  comments: [
    comment("a", "bob", "2026-11-01T10:00:00Z", {
      text: `Look at #${PART} please`,
      targetId: PART,
      targetLabel: "The second part",
    }),
    comment("b", "me", "2026-11-01T11:00:00Z"),
    comment("c", "bob", "2026-11-01T09:00:00Z", { resolved: true, resolvedBy: "me" }),
  ],
};

const settle = async () => {
  for (let i = 0; i < 3; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(more: Partial<ReviewPanelProps> = {}) {
  const props: ReviewPanelProps = {
    review: VIEW,
    me: "me",
    open: true,
    onClose: vi.fn(),
    onStatus: vi.fn(),
    onComment: vi.fn(async () => undefined),
    onResolve: vi.fn(),
    ...more,
  };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={DEFINITIONS}>
        <ReviewPanel {...props} />
      </ModelsProvider>
    ),
    container,
  );
  return props;
}

const panel = () => document.querySelector<HTMLElement>('[data-testid="review-panel"]')!;
const bubbles = () => [...document.querySelectorAll<HTMLElement>('[data-testid="review-comment"]')];
const button = (name: string) =>
  [...panel().querySelectorAll("button")].find((b) => b.textContent?.trim() === name) as HTMLButtonElement;

test("the status buttons are at the top, the current one pressed; another is a change", async () => {
  const props = show();
  await settle();
  const group = panel().querySelector('[role="group"]')!;
  const pressed = [...group.querySelectorAll("button")].map((b) => [b.textContent, b.getAttribute("aria-pressed")]);
  expect(pressed).toEqual([
    ["Unchecked", "false"],
    ["Errors found", "true"],
    ["Checked", "false"],
  ]);
  button("Checked").click();
  button("Errors found").click();
  expect(props.onStatus).toHaveBeenCalledTimes(1);
  expect(props.onStatus).toHaveBeenCalledWith("checked");
  expect(panel().querySelector('[data-testid="review-reviewed-by"]')?.textContent).toContain("Reviewed by bob");
});

test("the open comments, oldest first: the reader's on the right, others' on the left", async () => {
  show();
  await settle();
  expect(bubbles().map((b) => [b.textContent?.includes("Look at"), b.dataset.mine])).toEqual([
    [true, "false"],
    [false, "true"],
  ]);
  const [theirs, mine] = bubbles();
  expect(theirs!.className).toContain("self-start");
  expect(mine!.className).toContain("self-end");
  expect(theirs!.textContent).toContain("bob");
  expect(mine!.textContent).toContain("You");
  // (a reference to a part, inline: before the parts are read, the label the server kept)
  expect(theirs!.querySelector('[data-testid="review-ref"]')?.textContent).toBe("The second part");
  expect(theirs!.textContent).toContain("Look at The second part please");
});

test("the resolved ones are shown, faded, when asked for", async () => {
  show();
  await settle();
  expect(bubbles()).toHaveLength(2);
  const toggle = panel().querySelector<HTMLInputElement>('input[type="checkbox"]')!;
  expect(toggle.parentElement?.textContent).toContain("Show resolved (1)");
  toggle.click();
  await settle();
  expect(bubbles()).toHaveLength(3);
  const resolved = bubbles().find((b) => b.dataset.resolved === "true")!;
  expect(resolved.textContent).toContain("Resolved by me");
  expect(resolved.querySelector(".opacity-50")).not.toBeNull();
});

test("a comment is resolved by its button", async () => {
  const props = show();
  await settle();
  const first = bubbles()[0]!;
  [...first.querySelectorAll("button")].find((b) => b.textContent === "Resolve")!.click();
  expect(props.onResolve).toHaveBeenCalledWith("a");
});

test("a comment is sent by the button or Ctrl+Enter, and the box is emptied", async () => {
  const props = show();
  await settle();
  const box = panel().querySelector("textarea")!;
  const send = button("Send");
  expect(send.disabled).toBe(true);
  box.value = "  First  ";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  await settle();
  send.click();
  await settle();
  expect(props.onComment).toHaveBeenCalledWith("First");
  expect(box.value).toBe("");
  box.value = "Second";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true }));
  await settle();
  expect(props.onComment).toHaveBeenLastCalledWith("Second");
});

test("what was written is put back if the comment was not made", async () => {
  show({ onComment: vi.fn(async () => Promise.reject(new Error("no"))) });
  await settle();
  const box = panel().querySelector("textarea")!;
  box.value = "Keep me";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  await settle();
  button("Send").click();
  await settle();
  expect(box.value).toBe("Keep me");
});

test("a comment being sent says so, and cannot be resolved yet", async () => {
  show({
    review: { ...VIEW, comments: [{ ...comment("p", "me", "2026-11-03T00:00:00Z"), pending: true }] },
  });
  await settle();
  expect(bubbles()[0]!.textContent).toContain("Sending…");
  expect(bubbles()[0]!.textContent).not.toContain("Resolve");
});

test("closed, it is off to the right and inert; Escape and the close button close it", async () => {
  const [open, setOpen] = createSignal(true);
  const onClose = vi.fn(() => setOpen(false));
  const props: ReviewPanelProps = {
    review: VIEW,
    me: "me",
    get open() {
      return open();
    },
    onClose,
    onStatus: vi.fn(),
    onComment: vi.fn(async () => undefined),
    onResolve: vi.fn(),
  };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={DEFINITIONS}>
        <ReviewPanel {...props} />
      </ModelsProvider>
    ),
    container,
  );
  await settle();
  expect(panel().className).toContain("translate-x-0");
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  await settle();
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(panel().className).toContain("translate-x-full");
  expect(panel().getAttribute("aria-hidden")).toBe("true");
  // (Escape when it is closed does nothing)
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  expect(onClose).toHaveBeenCalledTimes(1);
  setOpen(true);
  await settle();
  panel().querySelector<HTMLButtonElement>('button[aria-label="Close the review"]')!.click();
  expect(onClose).toHaveBeenCalledTimes(2);
});

test("no comments says so", async () => {
  show({ review: { ...VIEW, comments: [], openComments: 0 } });
  await settle();
  expect(panel().textContent).toContain("No comments");
  expect(panel().querySelector('input[type="checkbox"]')).toBeNull();
});

test("a reference to a part is an inline chip (type and label) that shows the part on the page; one gone says so", async () => {
  document.body.insertAdjacentHTML("beforeend", `<div data-item-id="${PART}">The second part</div>`);
  const block = document.querySelector<HTMLElement>(`[data-item-id="${PART}"]`)!;
  const scrolled = vi.fn();
  block.scrollIntoView = scrolled;
  show({ parts: [{ id: PART, type: "Statement", label: "The second part, now renamed" }] });
  await settle();
  const chip = panel().querySelector<HTMLElement>('[data-testid="review-ref"]')!;
  expect(chip.tagName).toBe("BUTTON");
  expect(chip.textContent).toBe("StatementThe second part, now renamed");
  chip.click();
  expect(scrolled).toHaveBeenCalled();
  dispose?.();
  document.body.innerHTML = "";
  show({ parts: [] });
  await settle();
  const gone = panel().querySelector<HTMLElement>('[data-testid="review-ref"]')!;
  expect(gone.dataset.gone).toBe("true");
  expect(gone.textContent).toBe("The second part(no longer there)");
});

test("a comment made with a part but no reference to it in its text has the chip first", async () => {
  show({
    review: {
      ...VIEW,
      comments: [comment("x", "bob", "2026-11-01T10:00:00Z", { text: "Wrong", targetId: PART, targetLabel: "P" })],
    },
  });
  await settle();
  expect(bubbles()[0]!.querySelector("div.rounded-lg")?.textContent).toBe("P Wrong");
});
