import { createFeedReader } from "@pangloss/interface-core";
import type { ApiClient } from "@pangloss/interface-core";
import { action, createOptimisticStore, until } from "solid-js";
import { createType, editType, moveType } from "./api";
import type { NewType, TreeNode, TypeOut } from "./api";
import { findNode, parentOf, withAdded, withLabel, withMove } from "./tree";

/** The hierarchy as the page reads it: `loading` until the feed's first tree */
export interface TreeView {
  state: "loading" | "ready";
  nodes: TreeNode[];
}

/** How long a change waits for the feed to bring it back before it lets the optimistic version go */
export const ACKNOWLEDGE_TIMEOUT = 15_000;

/** A source of trees, as `treeFeed(type)` gives (`onstatus` is the connection's, set by the live source) */
export type TreeSource = AsyncIterable<TreeNode[]> & {
  onstatus?: (state: "connected" | "reconnecting" | "closed", error?: unknown) => void;
};

/**
 * The hierarchy of the typology `type`, from the feed, and what can be done to it. A move or a new label goes to the
 * API, is shown at once (optimistically), and is kept until the feed brings it back (or `ACKNOWLEDGE_TIMEOUT` has
 * passed: the next tree will have it). One that the API refuses is undone, and its promise rejects. Make it in a
 * component (one connection), and call the changes from event handlers.
 */
export function createTypeTree(options: {
  type: string;
  /** Opens the feed (`invoke(treeFeed, { signal }, type)`); the signal is aborted when the page no longer needs it */
  feed: (signal: AbortSignal) => TreeSource;
  api: ApiClient;
}) {
  const { type, api } = options;
  const read = createFeedReader(options.feed, api);
  const [tree, setTree] = createOptimisticStore<TreeView>(
    async function* () {
      // (one connection, closed when the page is left; a reconnect asks for a new access cookie: `createFeedReader`)
      for await (const nodes of read()) yield { state: "ready" as const, nodes };
    },
    { state: "loading", nodes: [] },
    { seedLoadingValue: true },
  );

  // (the feed's acknowledgement: a timeout is not a failure, as the change was made)
  function* acknowledged(predicate: () => boolean) {
    try {
      yield until(predicate, { timeout: ACKNOWLEDGE_TIMEOUT });
    } catch {
      // (the next tree brings it)
    }
  }

  const move = action(function* (id: string, to: string | null) {
    setTree((draft) => {
      draft.nodes = withMove(draft.nodes, id, to) as TreeNode[];
    });
    yield moveType(api, type, id, to);
    yield* acknowledged(() => (parentOf(tree.nodes, id)?.id ?? null) === to);
  });

  const rename = action(function* (id: string, label: string) {
    setTree((draft) => {
      draft.nodes = withLabel(draft.nodes, id, label) as TreeNode[];
    });
    yield editType(api, type, id, { label });
    yield* acknowledged(() => findNode(tree.nodes, id)?.label === label);
  });

  // (a type the API has made, shown in its place until the feed has it)
  const place = action(function* (made: TypeOut) {
    setTree((draft) => {
      draft.nodes = withAdded(draft.nodes, made, made.supertype) as TreeNode[];
    });
    yield* acknowledged(() => findNode(tree.nodes, made.id) !== undefined);
  });

  /** Makes a type; the promise is the API's answer (a refusal rejects), and the type is shown at once when it comes */
  async function add(fields: NewType): Promise<TypeOut> {
    const made = await createType(api, type, fields);
    place(made).catch(() => undefined);
    return made;
  }

  return { tree, move, rename, add };
}
