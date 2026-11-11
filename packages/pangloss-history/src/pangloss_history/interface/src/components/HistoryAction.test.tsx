// @vitest-environment happy-dom
import {
  ApiError,
  ApiProvider,
  ComponentsProvider,
  defaultComponents,
  ModelsProvider,
  ModulesProvider,
  SessionProvider,
  SidePanelProvider,
  ToastsProvider,
  useSidePanel,
  useToasts,
} from "@pangloss/interface-core";
import type { ApiClient, ConsoleActionProps, User } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { For } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { Listing, Version, VersionRecord } from "../api";
import { DEFINITIONS } from "../fixtures";

vi.mock("@solidjs/router", async (original) => ({
  ...(await original<typeof import("@solidjs/router")>()),
  revalidate: vi.fn(),
}));

const { default: HistoryAction } = await import("./HistoryAction");

const record = (version: number, op: VersionRecord["op"], more: Partial<VersionRecord> = {}): VersionRecord => ({
  seq: version,
  version,
  op,
  who: "ann",
  at: "2026-11-04T10:00:00Z",
  schemaPosition: {},
  restoredFrom: null,
  label: "Crowned",
  changes: [],
  ...more,
});

const LISTING: Listing = {
  id: "f1",
  model: "Factoid",
  currentVersion: 3,
  missing: [],
  versions: [
    record(1, "create"),
    record(2, "update", { who: "bob", changes: [{ key: "text", kind: "changed", count: 1 }] }),
    record(3, "update", { label: "Crowned at Rome", changes: [{ key: "statements", kind: "added", count: 1 }] }),
  ],
};

const CONTENT: Record<number, Version["content"]> = {
  1: { type: "Factoid", label: "Crowned", text: "The king is crowned", statements: [] },
  2: { type: "Factoid", label: "Crowned", text: "The emperor is crowned", statements: [] },
  3: {
    type: "Factoid",
    label: "Crowned at Rome",
    text: "The emperor is crowned",
    statements: [{ id: "s1", type: "Statement", label: "A statement", text: "x" }],
  },
};

const version = (n: number): Version => ({
  ...LISTING.versions[n - 1]!,
  content: CONTENT[n]!,
  upgraded: false,
  problems: [],
});

function client(
  options: {
    listing?: Listing | "none";
    post?: ApiClient["post"];
    // (how a version is read: by default at once)
    read?: (n: number) => Promise<Version>;
  } = {},
): ApiClient {
  return {
    baseUrl: "/api",
    get: vi.fn(async (path: string) => {
      if (path === "/Factoid/f1/history") {
        if (options.listing === "none") throw new ApiError(404, "There is no history");
        return options.listing ?? LISTING;
      }
      const found = /\/history\/(\d+)$/.exec(path);
      if (found) return options.read ? options.read(Number(found[1])) : version(Number(found[1]));
      throw new Error(`not expected: ${path}`);
    }) as never,
    post: options.post ?? (vi.fn(async () => ({ id: "f1", version: 4, restoredFrom: 1 })) as never),
    put: vi.fn() as never,
    patch: vi.fn() as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
  };
}

function ShownToasts() {
  const toasts = useToasts();
  return (
    <ul>
      <For each={toasts?.toasts() ?? []}>
        {(toast) => (
          <li data-testid="toast" data-tone={toast.tone}>
            {toast.message}
          </li>
        )}
      </For>
    </ul>
  );
}

// (another panel on the right, as review's is)
let other: ReturnType<typeof useSidePanel> | undefined;
function OtherPanel() {
  other = useSidePanel("review");
  return <span data-testid="other" data-open={other.open() ? "true" : "false"} />;
}

const me = { username: "me", email: "m@example.org", fullName: null, admin: false } as User;
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(props: Partial<ConsoleActionProps> = {}, user: User | null = me, api = client()) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={defaultComponents}>
        <SessionProvider user={() => user ?? undefined}>
          <ApiProvider client={api}>
            <ModelsProvider definitions={DEFINITIONS}>
              <ModulesProvider modules={[]}>
                <ToastsProvider>
                  <SidePanelProvider>
                    <HistoryAction
                      type="Factoid"
                      id="f1"
                      model={DEFINITIONS.models.Factoid!}
                      page="item"
                      {...props}
                    />
                    <OtherPanel />
                  </SidePanelProvider>
                  <ShownToasts />
                </ToastsProvider>
              </ModulesProvider>
            </ModelsProvider>
          </ApiProvider>
        </SessionProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return api;
}

const settle = async () => {
  for (let i = 0; i < 8; i++) await new Promise((resolve) => setTimeout(resolve));
};
const $ = (selector: string) => document.querySelector<HTMLElement>(selector);
const $$ = (selector: string) => [...document.querySelectorAll<HTMLElement>(selector)];
const button = () => $('[data-testid="history-button"]')?.closest("button");
const openPanel = async () => {
  button()!.click();
  await settle();
};

test("there is no button for someone who is not logged in, nor on the edit page", async () => {
  show({}, null);
  await settle();
  expect(button()).toBeFalsy();
  dispose?.();
  show({ page: "edit" });
  await settle();
  expect(button()).toBeFalsy();
});

test("the panel lists the versions newest first, condensed, the current one marked", async () => {
  const api = show();
  await openPanel();
  expect($('[data-testid="history-panel"]')!.dataset.open).toBe("true");
  expect(api.get).toHaveBeenCalledWith("/Factoid/f1/history", { summary: true });
  const cards = $$('[data-testid="history-version"]');
  expect(cards.map((card) => card.dataset.version)).toEqual(["3", "2", "1"]);
  expect(cards[0]!.querySelector('[data-testid="history-current"]')).toBeTruthy();
  expect(cards[1]!.querySelector('[data-testid="history-current"]')).toBeFalsy();
  // (a label only where it is a new one; the fields that changed as tags)
  expect(cards.map((card) => card.querySelector('[data-testid="history-label"]')?.textContent)).toEqual([
    "Crowned at Rome",
    undefined,
    "Crowned",
  ]);
  expect(cards[0]!.querySelector('[data-testid="history-change"]')!.textContent).toBe("+1 statements");
  expect(cards[1]!.textContent).toContain("bob");
});

test("opening the history closes another panel on the right, and the other way round", async () => {
  show();
  other!.setOpen(true);
  await settle();
  await openPanel();
  expect($('[data-testid="other"]')!.dataset.open).toBe("false");
  other!.setOpen(true);
  await settle();
  expect($('[data-testid="history-panel"]')!.dataset.open).toBe("false");
});

test("a version clicked slides out beside the panel, as the item's page shows it; clicked again it goes back", async () => {
  const api = show();
  await openPanel();
  expect($('[data-testid="history-drawer"]')!.dataset.open).toBe("false");
  $('[data-testid="history-version"][data-version="1"]')!.click();
  await settle();
  expect(api.get).toHaveBeenCalledWith("/Factoid/f1/history/1", { view: true });
  const drawer = $('[data-testid="history-drawer"]')!;
  expect(drawer.dataset.open).toBe("true");
  expect(drawer.dataset.version).toBe("1");
  expect(drawer.textContent).toContain("The king is crowned");
  expect($('[data-testid="history-restore"]')).toBeTruthy();
  $('[data-testid="history-version"][data-version="1"]')!.click();
  await settle();
  expect(drawer.dataset.open).toBe("false");
});

test("the current version cannot be restored", async () => {
  show();
  await openPanel();
  $('[data-testid="history-version"][data-version="3"]')!.click();
  await settle();
  expect($('[data-testid="history-restore"]')).toBeFalsy();
});

test("restore asks first, listing the versions undone and what will change, then restores and says so", async () => {
  const api = show();
  await openPanel();
  $('[data-testid="history-version"][data-version="1"]')!.click();
  await settle();
  $('[data-testid="history-restore"]')!.click();
  await settle();
  const dialog = $('[data-testid="history-restore-dialog"]')!;
  expect($$('[data-testid="history-undone"]').map((row) => row.textContent?.match(/v\d/)?.[0])).toEqual(["v3", "v2"]);
  const changes = $$('[data-testid="history-change-row"]');
  expect(changes.map((row) => [row.dataset.kind, row.querySelector('[data-testid="history-trail"]')!.textContent])).toEqual([
    ["changed", "Label"],
    ["changed", "text"],
    ["removed", "statements"],
  ]);
  // (the words of the text that changed)
  const words = changes[1]!.querySelectorAll('[data-testid="history-words"] [data-kind]');
  expect([...words].map((w) => `${(w as HTMLElement).dataset.kind}:${w.textContent}`)).toContain("removed:emperor");
  expect(dialog.textContent).toContain("Nothing is erased");

  $('[data-testid="history-restore-confirm"]')!.click();
  await settle();
  expect(api.post).toHaveBeenCalledWith("/Factoid/f1/history/1/restore", undefined, { headers: { "If-Match": '"3"' } });
  expect($('[data-testid="history-restore-dialog"]')).toBeFalsy();
  expect($('[data-testid="toast"]')!.textContent).toBe("Restored version 1 as version 4");
  expect($('[data-testid="history-drawer"]')!.dataset.open).toBe("false");
});

test("while what the item is now is being read, the dialog says so and Restore waits", async () => {
  let release: (() => void) | undefined;
  const read = (n: number) =>
    n === 3 ? new Promise<Version>((resolve) => (release = () => resolve(version(3)))) : Promise.resolve(version(n));
  show({}, me, client({ read }));
  await openPanel();
  $('[data-testid="history-version"][data-version="1"]')!.click();
  await settle();
  $('[data-testid="history-restore"]')!.click();
  await settle();
  // (not "Nothing: the content is the same": it is not known yet)
  expect($('[data-testid="history-restore-changes"]')!.dataset.state).toBe("reading");
  expect($('[data-testid="history-restore-dialog"]')!.textContent).not.toContain("the content is the same");
  expect(($('[data-testid="history-restore-confirm"]') as HTMLButtonElement).disabled).toBe(true);
  release!();
  await settle();
  expect($('[data-testid="history-restore-changes"]')!.dataset.state).toBe("known");
  expect($$('[data-testid="history-change-row"]').length).toBe(3);
  expect(($('[data-testid="history-restore-confirm"]') as HTMLButtonElement).disabled).toBe(false);
});

test("what the item is now that cannot be read is said in the dialog, with why", async () => {
  const read = (n: number) =>
    n === 3 ? Promise.reject(new ApiError(500, "The server fell over")) : Promise.resolve(version(n));
  show({}, me, client({ read }));
  await openPanel();
  $('[data-testid="history-version"][data-version="1"]')!.click();
  await settle();
  $('[data-testid="history-restore"]')!.click();
  await settle();
  expect($('[data-testid="history-restore-changes"]')!.dataset.state).toBe("unreadable");
  expect($('[data-testid="history-restore-unreadable"]')!.textContent).toContain("The server fell over");
  expect($$('[data-testid="history-change-row"]').length).toBe(0);
  // (what the restore undoes is still listed, so it may go on)
  expect($$('[data-testid="history-undone"]').length).toBe(2);
  expect(($('[data-testid="history-restore-confirm"]') as HTMLButtonElement).disabled).toBe(false);
});

test("a restore refused because the item changed meanwhile is said in a red toast", async () => {
  const post = vi.fn(async () => {
    throw new ApiError(412, "changed");
  });
  show({}, me, client({ post: post as never }));
  await openPanel();
  $('[data-testid="history-version"][data-version="2"]')!.click();
  await settle();
  $('[data-testid="history-restore"]')!.click();
  await settle();
  $('[data-testid="history-restore-confirm"]')!.click();
  await settle();
  const toast = $('[data-testid="toast"]')!;
  expect(toast.dataset.tone).toBe("error");
  expect(toast.textContent).toContain("changed meanwhile");
});

test("an item with nothing recorded says why, and how to record it", async () => {
  show({}, me, client({ listing: "none" }));
  await openPanel();
  expect($('[data-testid="history-none"]')!.textContent).toContain("pangloss history baseline");
  expect($('[data-testid="history-compare"]')).toBeFalsy();
});

test("versions not recorded are a gap in their place", async () => {
  show({}, me, client({ listing: { ...LISTING, missing: [2], versions: [LISTING.versions[0]!, LISTING.versions[2]!] } }));
  await openPanel();
  expect($('[data-testid="history-gap"]')!.textContent).toBe("Version 2 was not recorded");
});
