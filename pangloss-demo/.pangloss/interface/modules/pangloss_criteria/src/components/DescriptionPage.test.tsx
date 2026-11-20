// @vitest-environment happy-dom
import { createItemFormState, getModel, ItemFormProvider, SessionProvider } from "@pangloss/interface-core";
import type { FormData, User } from "@pangloss/interface-core";
import { afterEach, expect, test, vi } from "vitest";
import type { MentionsPage } from "../api";
import { addFilter, button, byLabel, byTestId, cleanUp, click, definitions, fakeApi, MARIE, SECRETARY, settle, show, type } from "../testing";
import DescriptionCriteria from "./DescriptionCriteria";
import DescriptionPage from "./DescriptionPage";

afterEach(cleanUp);

const ANN = { username: "ann", email: "ann@example.com", admin: false } as unknown as User;

const item = {
  type: "Description",
  id: SECRETARY,
  label: "The duke's secretary",
  criteria: { type: "Person", where: { born: { eq: 1500 } } },
  meta: {},
};

const mention = (n: number) => ({
  id: `m${n}`,
  wording: n === 1 ? "N. N., secretarius" : null,
  criteria: n === 1 ? { type: "Person", where: { born: { eq: 1501 } } } : null,
  head: { id: `s${n}`, type: "Sighting", label: `Seen at place ${n}` },
});

const mentions = (count: number, page = 1): MentionsPage => ({
  count,
  page,
  pageSize: 25,
  results: Array.from({ length: Math.min(25, count - (page - 1) * 25) }, (_, at) => mention((page - 1) * 25 + at + 1)),
});

/** What `ItemContents` is given (the item without its criteria), shown as its keys */
function Contents(props: { item: Record<string, unknown> }) {
  return <div data-testid="contents">{Object.keys(props.item).sort().join(",")}</div>;
}

function page(count: number, user?: User) {
  const api = fakeApi((path, body) => {
    if (path === `/criteria/shared/${SECRETARY}/mentions`) return mentions(count, Number((body as Record<string, unknown>).page));
    if (path === "/criteria/preview") return { count: 1, tooBroad: false, candidates: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }] };
    return { found: [] };
  });
  show(
    api.client,
    () => (
      <SessionProvider user={() => user}>
        <DescriptionPage type="Description" id={SECRETARY} item={item} model={getModel(definitions, "Description")!} />
      </SessionProvider>
    ),
    { ItemContents: Contents },
  );
  return api.asked;
}

test("its page says first how many mentions use it, and that this does not make them one; then its criteria", async () => {
  page(214);
  await vi.waitFor(() => expect(byTestId("description-used-by")).not.toBeNull());
  expect(byTestId("description-used-by")?.textContent).toBe(
    "A description used by 214 mentions. It does not say that they are one and the same.",
  );
  expect(byTestId("description-intro")?.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("Person · born: 1500");
  // (the criteria are not shown again as a raw field)
  expect(byTestId("contents")?.textContent).toBe("id,label,meta,type");
});

test("one mention, and none", async () => {
  page(1);
  await vi.waitFor(() => expect(byTestId("description-used-by")?.textContent).toBe("A description used by 1 mention. It does not say that they are one and the same."));
  cleanUp();
  page(0);
  await vi.waitFor(() => expect(byTestId("description-used-by")?.textContent).toBe("A description that no mention uses yet."));
  expect(byTestId("description-no-mentions")?.textContent).toBe("No mention cites it yet.");
});

test("its mentions: the document of each as a chip at the mention, the wording, the conditions of its own; a page at a time", async () => {
  const asked = page(30);
  await vi.waitFor(() => expect(document.body.querySelectorAll('[data-testid="description-mention"]')).toHaveLength(25));
  const first = document.body.querySelector('[data-testid="description-mention"]')!;
  expect(first.querySelector("a")?.getAttribute("href")).toBe("/Sighting/s1?show=m1");
  expect(first.textContent).toContain("Seen at place 1");
  expect(first.querySelector('[data-testid="criteria-wording"]')?.textContent).toBe("“N. N., secretarius”");
  expect(first.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("Person · born: 1501");
  // (the first page is read once, for the count and the list)
  expect(asked.filter((each) => each.path.endsWith("/mentions"))).toHaveLength(1);
  const next = [...byTestId("description-mentions")!.querySelectorAll("button")].find((each) => /next/i.test(each.getAttribute("aria-label") ?? each.textContent ?? ""));
  click(next);
  await vi.waitFor(() => expect(document.body.querySelectorAll('[data-testid="description-mention"]')).toHaveLength(5));
  expect(asked.filter((each) => each.path.endsWith("/mentions")).at(-1)!.body).toMatchObject({ page: 2, page_size: 25 });
});

test("what its criteria find, for someone logged in; a reader is told to log in, and nothing is asked", async () => {
  const asked = page(2, ANN);
  await vi.waitFor(() => expect(byTestId("description-candidates")?.querySelector('[data-testid="criteria-count"]')?.textContent).toBe("1 candidate found"));
  expect(asked.find((each) => each.path === "/criteria/preview")!.body).toEqual({ criteria: item.criteria, named: [] });
  expect(byTestId("description-candidates")?.textContent).toContain("Marie of Burgundy");
  cleanUp();
  const anonymous = page(2);
  await vi.waitFor(() => expect(byTestId("description-candidates-login")).not.toBeNull());
  expect(anonymous.some((each) => each.path === "/criteria/preview")).toBe(false);
});

// --- its form -----------------------------------------------------------------------------------------------------------

function form(initial: FormData, type = "Description") {
  const api = fakeApi((path) =>
    path === "/criteria/preview" ? { count: 0, tooBroad: false, candidates: [] } : { found: [] },
  );
  const state = createItemFormState(initial);
  show(api.client, () => (
    <ItemFormProvider state={state}>
      <dl>
        <DescriptionCriteria type={type} model={getModel(definitions, type)!} />
      </dl>
    </ItemFormProvider>
  ));
  return { state, asked: api.asked };
}

test("a new one: the class first, then the search form, written into the form's criteria as it changes", async () => {
  const { state, asked } = form({ type: "Description", label: "" } as FormData);
  await vi.waitFor(() => expect(byTestId("description-choose-type")).not.toBeNull());
  const person = [...byTestId("description-choose-type")!.querySelectorAll("button")].find((each) => each.textContent?.includes("Person"));
  click(person);
  await vi.waitFor(() => expect(byLabel("Add a filter")).not.toBeNull());
  expect(byTestId("criteria-need-condition")).not.toBeNull();
  addFilter("born");
  type("born", "1500");
  await settle(300);
  expect(state.get(["criteria"])).toEqual({ type: "Person", where: { born: { eq: 1500 } } });
  // (with what the criteria find)
  await vi.waitFor(() => expect(byTestId("criteria-count")?.textContent).toBe("No candidates yet: it will update as data is added"));
  expect(asked.find((each) => each.path === "/criteria/preview")!.body).toEqual({ criteria: { type: "Person", where: { born: { eq: 1500 } } }, named: [] });
  // (Back: another class, and the criteria go)
  click(button("Back"));
  expect(state.get(["criteria"])).toBeNull();
  expect(byTestId("description-choose-type")).not.toBeNull();
});

test("a saved one opens in the search form of its class, with its criteria", async () => {
  const { state } = form({ ...item } as FormData);
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1500"));
  type("born", "1600");
  await settle(300);
  expect(state.get(["criteria"])).toEqual({ type: "Person", where: { born: { eq: 1600 } } });
});

test("the row is in the form of a shared description only", async () => {
  form({ type: "Sighting" } as FormData, "Sighting");
  await settle();
  expect(byTestId("description-choose-type")).toBeNull();
  expect(byTestId("description-criteria")).toBeNull();
});
