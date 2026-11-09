import { isSafeError } from "@solidjs/web";
import { expect, test } from "vitest";
import { contextPath, contextTrail, headOf, wrappingSpaces } from "./context";
import { ApiError, createApiClient, problemsOf, queryString } from "./client";
import {
  autocomplete,
  createItem,
  updateItem,
  getCurrentUser,
  getItem,
  listItems,
  logIn,
  logOut,
  references,
  searchItems,
  withCurrentReferences,
} from "./fetch";
import type { ModelDefinitions } from "../types";

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

test("an ApiError may be sent from the server render, and is still one when it arrives", () => {
  // (the built server puts "Internal Server Error" in place of an error that is not marked safe)
  const error = new ApiError(404, "There is no Place with id n1", { detail: "There is no Place with id n1" });
  expect(isSafeError(error)).toBe(true);
  // what the browser is given is a plain Error with the properties
  const arrived = Object.assign(new Error(error.message), { name: "ApiError", status: 404, detail: error.detail });
  expect(arrived instanceof ApiError).toBe(true);
  expect((arrived as ApiError).status).toBe(404);
  // ... and nothing else is one
  expect(new Error("404 Not Found") instanceof ApiError).toBe(false);
  expect(Object.assign(new Error("x"), { name: "ApiError" }) instanceof ApiError).toBe(false);
  for (const other of [null, undefined, "ApiError", 404] as unknown[]) {
    expect(other instanceof ApiError).toBe(false);
  }
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
  await searchItems(client, {
    type: "Factoid",
    where: { label: { contains: "x" } },
    orderBy: [{ field: "year", direction: "desc" }],
    pageSize: 10,
  });
  expect(calls[0]!.init.method).toBe("POST");
  expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
    type: "Factoid",
    where: { label: { contains: "x" } },
    order_by: [{ field: "year", direction: "desc" }],
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

test("only an item inside another has a head node to go to", () => {
  const item = (meta?: object) => ({ id: "2", type: "Activity", label: "x", meta });
  expect(headOf(item())).toBeUndefined();
  expect(headOf(item({ isHeadNode: true, headNodeType: null, headNodeId: null }))).toBeUndefined();
  expect(headOf(item({ isHeadNode: false, headNodeType: "Factoid", headNodeId: "1" }))).toEqual({
    type: "Factoid",
    id: "1",
  });
});

test("the head of an item from its whole meta, which has no isHeadNode: a head node's head is itself", () => {
  const meta = (headNodeType: string, headNodeId: string) =>
    ({ version: 1, published: true, reviewStatus: null, createdBy: null, createdWhen: "", updatedBy: null, updatedWhen: null, headNodeType, headNodeId });
  expect(headOf({ id: "1", meta: meta("Factoid", "1") })).toBeUndefined();
  expect(headOf({ id: "2", meta: meta("Factoid", "1") })).toEqual({ type: "Factoid", id: "1" });
});

test("the trail has the spaces and the documents between them, but not the item itself", () => {
  expect(contextTrail(undefined)).toEqual([]);
  expect(
    contextTrail(
      [
        { type: "Negative", contents: [{ type: "Order", id: "1" }, { type: "Action", id: "2" }] },
        { type: "Hypothetical" },
      ],
      "2",
    ),
  ).toEqual(["Negative", "Order", "Hypothetical"]);
  expect(contextTrail([{ type: "#rootcontext", contents: [{ type: "Order", id: "1" }] }])).toEqual(["Order"]);
});

test("the path round an item gives the id of each document, and of a space none", () => {
  expect(
    contextPath([{ type: "Negative", contents: [{ type: "Order", id: "1" }, { type: "Action", id: "2" }] }], "2"),
  ).toEqual([{ type: "Negative" }, { type: "Order", id: "1" }]);
});

test("an item is created by a POST of the body, and updated by a PUT that says which version it is based on", async () => {
  const { client, calls } = clientAnswering(() => json({ id: "n1", type: "Place", label: "Rome" }, 201));
  await createItem(client, "Place", { label: "Rome" });
  expect(calls[0]!.url).toBe("http://api.test/api/Place");
  expect(calls[0]!.init).toMatchObject({ method: "POST", body: '{"label":"Rome"}' });
  await updateItem(client, "Place", "n1", { id: "n1", label: "Roma" }, 3);
  expect(calls[1]!.url).toBe("http://api.test/api/Place/n1");
  expect(calls[1]!.init.method).toBe("PUT");
  expect(calls[1]!.init.headers).toMatchObject({ "If-Match": '"3"', "Content-Type": "application/json" });
});

test("a 412 keeps what else the API said, and a 422 is read as a line for each problem", async () => {
  const stale = clientAnswering(() => json({ detail: "Stale", currentVersion: 4 }, 412));
  const error = (await updateItem(stale.client, "Place", "n1", {}, 3).catch((e: unknown) => e)) as ApiError;
  expect(error.status).toBe(412);
  expect(error.body).toMatchObject({ currentVersion: 4 });
  const invalid = new ApiError(
    422,
    JSON.stringify([
      { loc: ["body", "statements", 0, "text"], msg: "too short" },
      { loc: [], msg: "odd" },
    ]),
  );
  expect(problemsOf(invalid)).toEqual(["statements › 0 › text: too short", "odd"]);
  expect(problemsOf(new ApiError(409, "Id in use"))).toEqual(["Id in use"]);
});

test("which entities are still there is one request with every id; with none, no request", async () => {
  const { client, calls } = clientAnswering(() => json({ found: [{ id: "p1", type: "Person", label: "Alice Smith" }] }));
  expect(await references(client, [])).toEqual([]);
  expect(calls).toEqual([]);
  expect(await references(client, ["p1", "p2"])).toEqual([{ id: "p1", type: "Person", label: "Alice Smith" }]);
  expect(calls[0]!.url).toBe("http://api.test/api/references");
  expect(calls[0]!.init.method).toBe("POST");
  expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ ids: ["p1", "p2"] });
});

test("a stashed item is brought up to date with what the API says of its entities", async () => {
  const definitions = { models: { Person: { name: "Person", kind: "Entity" } }, enums: {} } as unknown as ModelDefinitions;
  const { client } = clientAnswering(() => json({ found: [{ id: "p1", type: "Person", label: "Alice Smith" }] }));
  const refreshed = await withCurrentReferences(client, definitions, {
    type: "Note",
    people: [
      { type: "Person", id: "p1", label: "Alice" },
      { type: "Person", id: "p2", label: "Bob" },
    ],
  });
  expect(refreshed.value.people).toEqual([{ type: "Person", id: "p1", label: "Alice Smith" }]);
  expect(refreshed.gone).toEqual([{ type: "Person", id: "p2", label: "Bob" }]);
});
