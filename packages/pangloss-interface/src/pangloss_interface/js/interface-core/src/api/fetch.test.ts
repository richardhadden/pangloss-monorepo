import { expect, test } from "vitest";
import { wrappingSpaces } from "./context";
import { ApiError, createApiClient, queryString } from "./client";
import {
  autocomplete,
  getCurrentUser,
  getItem,
  listItems,
  logIn,
  logOut,
  searchItems,
} from "./fetch";

type Call = { url: string; init: RequestInit };

/** A client whose `fetch` records what it is asked and answers with `respond` */
function clientAnswering(respond: (url: string) => Response) {
  const calls: Call[] = [];
  const client = createApiClient({
    baseUrl: "http://api.test/api",
    fetch: async (url, init) => {
      calls.push({ url: String(url), init: init ?? {} });
      return respond(String(url));
    },
  });
  return { client, calls };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("a query string leaves out what is not given, and repeats lists", () => {
  expect(queryString({ q: "ro me", page: 2, deep: undefined, empty: "" })).toBe("?q=ro+me&page=2");
  expect(queryString({ type: ["Person", "Place"] })).toBe("?type=Person&type=Place");
  expect(queryString()).toBe("");
});

test("a list is asked for by type, with the names the API uses", async () => {
  const page = { results: [], count: 0, page: 2, pageSize: 5, nextPage: null, previousPage: 1 };
  const { client, calls } = clientAnswering(() => json(page));
  expect(await listItems(client, "Place", { q: "rom", page: 2, pageSize: 5 })).toEqual(page);
  expect(calls[0]!.url).toBe("http://api.test/api/Place?q=rom&page=2&page_size=5");
  expect(calls[0]!.init.credentials).toBe("include");
});

test("deep is sent only when it is on", async () => {
  const { client, calls } = clientAnswering(() => json({}));
  await listItems(client, "Place", { deep: false });
  await listItems(client, "Place", { deep: true });
  expect(calls.map((call) => call.url)).toEqual([
    "http://api.test/api/Place",
    "http://api.test/api/Place?deep=true",
  ]);
});

test("the id of an item is escaped, as it can be a URL", async () => {
  const { client, calls } = clientAnswering(() => json({ id: "x" }));
  await getItem(client, "Person", "https://example.org/a b");
  expect(calls[0]!.url).toBe("http://api.test/api/Person/https%3A%2F%2Fexample.org%2Fa%20b");
});

test("a failure is an ApiError with the status and what the API said", async () => {
  const { client } = clientAnswering(() => json({ detail: "No such Person" }, 404));
  const error = await getItem(client, "Person", "x").catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 404, detail: "No such Person" });
});

test("a 422 with a list of problems is kept as text; a body that is not JSON uses the status text", async () => {
  const problems = clientAnswering(() => json({ detail: [{ loc: ["body", "q"], msg: "bad" }] }, 422));
  const error = (await listItems(problems.client, "Place").catch((e: unknown) => e)) as ApiError;
  expect(error.status).toBe(422);
  expect(error.detail).toContain('"msg":"bad"');
  const plain = clientAnswering(() => new Response("oops", { status: 500, statusText: "Server Error" }));
  expect(await listItems(plain.client, "Place").catch((e: unknown) => e)).toMatchObject({
    status: 500,
    detail: "Server Error",
  });
});

test("autocomplete repeats the types", async () => {
  const { client, calls } = clientAnswering(() => json({ results: [] }));
  await autocomplete(client, { q: "ro", types: ["Person", "Place"], pageSize: 5 });
  expect(calls[0]!.url).toBe("http://api.test/api/autocomplete?q=ro&type=Person&type=Place&page_size=5");
});

test("a search is posted as JSON", async () => {
  const { client, calls } = clientAnswering(() => json({ results: [] }));
  await searchItems(client, { type: "Factoid", where: { label: "x" }, pageSize: 10 });
  expect(calls[0]!.init.method).toBe("POST");
  expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
    type: "Factoid",
    where: { label: "x" },
    page_size: 10,
  });
});

test("no one logged in is undefined, not an error; other failures still are", async () => {
  const anonymous = clientAnswering(() => json({ detail: "Not authenticated" }, 401));
  expect(await getCurrentUser(anonymous.client)).toBeUndefined();
  const broken = clientAnswering(() => json({ detail: "boom" }, 500));
  await expect(getCurrentUser(broken.client)).rejects.toMatchObject({ status: 500 });
  const loggedIn = clientAnswering(() => json({ username: "demo", admin: true }));
  expect(await getCurrentUser(loggedIn.client)).toMatchObject({ username: "demo" });
});

test("an access cookie that has run out is refreshed once, and the user asked for again", async () => {
  let fresh = false;
  const { client, calls } = clientAnswering((url) => {
    if (url.endsWith("/users/session/refresh")) {
      fresh = true;
      return json({ message: "success" });
    }
    return fresh ? json({ username: "demo" }) : json({ detail: "Expired" }, 401);
  });
  expect(await getCurrentUser(client, { refresh: true })).toMatchObject({ username: "demo" });
  expect(calls.map((call) => call.url.replace("http://api.test/api", ""))).toEqual([
    "/users/me",
    "/users/session/refresh",
    "/users/me",
  ]);
  expect(calls[1]!.init.method).toBe("POST");
  expect(calls[1]!.init.body).toBeUndefined();
});

test("without a refresh cookie, or without asking to refresh, no one is logged in", async () => {
  const none = clientAnswering(() => json({ detail: "Not authenticated" }, 401));
  expect(await getCurrentUser(none.client, { refresh: true })).toBeUndefined();
  expect(none.calls).toHaveLength(2);
  const dontTry = clientAnswering(() => json({ detail: "Not authenticated" }, 401));
  expect(await getCurrentUser(dontTry.client)).toBeUndefined();
  expect(dontTry.calls).toHaveLength(1);
});

test("logging in sends the form the API wants, and a wrong password says what the API said", async () => {
  const ok = clientAnswering(() => json({ message: "success" }));
  await logIn(ok.client, "demo", "p&ss word");
  expect(ok.calls[0]!.url).toBe("http://api.test/api/users/session");
  expect(ok.calls[0]!.init.method).toBe("POST");
  expect(new Headers(ok.calls[0]!.init.headers).get("Content-Type")).toBe(
    "application/x-www-form-urlencoded",
  );
  expect(ok.calls[0]!.init.body).toBe("username=demo&password=p%26ss+word");
  expect(ok.calls[0]!.init.credentials).toBe("include");

  const wrong = clientAnswering(() => json({ detail: "Incorrect username or password" }, 401));
  await expect(logIn(wrong.client, "demo", "x")).rejects.toMatchObject({
    status: 401,
    detail: "Incorrect username or password",
  });
});

test("logging out deletes the session", async () => {
  const { client, calls } = clientAnswering(() => json({ message: "success" }));
  await logOut(client);
  expect(calls[0]!.init.method).toBe("DELETE");
  expect(calls[0]!.url).toBe("http://api.test/api/users/session");
});

test("an item is wrapped in the spaces of its context labels, outermost first, not in documents", () => {
  expect(wrappingSpaces(undefined)).toEqual([]);
  expect(wrappingSpaces(null)).toEqual([]);
  expect(wrappingSpaces([{ type: "#rootcontext", contents: [{ type: "Order", id: "1" }] }])).toEqual([]);
  expect(
    wrappingSpaces([
      { type: "#rootcontext", contents: [{ type: "Order", id: "1" }] },
      { type: "Negative", contents: [] },
      { type: "Subjunctive", contents: [{ type: "Action", id: "2" }] },
    ]),
  ).toEqual(["Negative", "Subjunctive"]);
});
