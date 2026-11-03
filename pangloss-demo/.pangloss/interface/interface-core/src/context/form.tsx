import { createContext, createSignal, createStore, snapshot, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import { getAt, removeAt, setAt } from "../schema";
import type { FieldProblem, FormData, FormHook, Path } from "../schema";

/** A problem, and the row of the form it is shown at (none: it is told elsewhere, in the toast) */
export interface PlacedProblem {
  problem: FieldProblem;
  row: Path | undefined;
}

/**
 * The item being edited by a form: a store (so that the field being typed in is changed, and
 * not the whole tree, and keeps the focus), read and written by path.
 */
export interface ItemFormState {
  /** What is at `path` (reactive) */
  get: (path: Path) => unknown;
  set: (path: Path, value: unknown) => void;
  /** Takes out an item of a list, or a key of an object */
  remove: (path: Path) => void;
  /** The whole item as it is now, a plain copy */
  plain: () => FormData;
  /** The id of the item, if it is one that exists (not one being made): what is cut from it and pasted back keeps its ids */
  headId?: string;
  /**
   * What is wrong (found when it was saved), each at the row of the form it is shown at: the row
   * with the longest path that the problem is under. Changing a value takes away the problems in it.
   */
  problems: Accessor<PlacedProblem[]>;
  /** Shows these problems instead of those shown; gives them back placed */
  setProblems: (problems: FieldProblem[]) => PlacedProblem[];
  /** The problems shown at the row of `path` (reactive) */
  problemsAt: (path: Path) => FieldProblem[];
  /** Says that a row of the form shows the field at `path`, for as long as it is there: call what it gives back to take it away */
  registerRow: (path: Path) => () => void;
}

const keyOf = (path: Path) => JSON.stringify(path);
const startsWith = (path: Path, prefix: Path) => prefix.length <= path.length && prefix.every((key, at) => path[at] === key);

/** What a form does beside keeping the item (see `createItemFormState`) */
export interface ItemFormOptions {
  /** The id of the item, if it is one that exists */
  headId?: string;
  /**
   * Given every object that is set (an item added, a type chosen, what is pasted), and what it gives back is set
   * instead: what a new item in this form starts with (see `fillEmbedded`)
   */
  fill?: (item: FormData) => FormData;
  /**
   * What is done around each change: the bindings of the models (a field copied to the fields of what its relation
   * holds, as it changes: `createBinder`) and their shares (`createSharer`), as one (`composeHooks`)
   */
  binder?: FormHook<unknown>;
}

/** Starts from a copy of `initial` */
export function createItemFormState(initial: FormData, options: ItemFormOptions = {}): ItemFormState {
  const { headId, fill, binder } = options;
  const [data, setData] = createStore<FormData>(structuredClone(initial));
  const [problems, setPlaced] = createSignal<PlacedProblem[]>([]);
  // (the rows on the page, by path: a plain count, read only when problems are placed)
  const rows = new Map<string, number>();
  const rowOf = (path: Path): Path | undefined => {
    for (let length = path.length; length >= 0; length -= 1) {
      if (rows.has(keyOf(path.slice(0, length)))) return path.slice(0, length);
    }
    return undefined;
  };
  // (what is changed at `path` is no longer what was found wrong: what is in it, and what it is in, such as a list too short)
  const clearAt = (path: Path) => {
    if (problems().length === 0) return;
    setPlaced((all) =>
      all.filter(({ problem }) => !startsWith(problem.path, path) && !startsWith(path, problem.path)),
    );
  };
  return {
    get: (path) => getAt(data, path),
    set: (path, value) => {
      const next = fill && typeof value === "object" && value !== null && !Array.isArray(value) ? fill(value as FormData) : value;
      const pending = binder?.before(data, path, typeof next === "object" && next !== null) ?? [];
      setData((draft) => {
        setAt(draft, path, next);
        binder?.after(draft, pending);
      });
      clearAt(path);
    },
    remove: (path) => {
      const pending = binder?.before(data, path, false) ?? [];
      setData((draft) => {
        removeAt(draft, path);
        binder?.after(draft, pending);
      });
      // (the places after it in a list move up: what was found in the list is no longer where it was)
      clearAt(typeof path.at(-1) === "number" ? path.slice(0, -1) : path);
    },
    plain: () => snapshot(data) as FormData,
    headId,
    problems,
    setProblems: (found) => {
      const placed = found.map((problem) => ({ problem, row: rowOf(problem.path) }));
      setPlaced(placed);
      return placed;
    },
    problemsAt: (path) => {
      const key = keyOf(path);
      return problems()
        .filter(({ row }) => row !== undefined && keyOf(row) === key)
        .map(({ problem }) => problem);
    },
    registerRow: (path) => {
      const key = keyOf(path);
      rows.set(key, (rows.get(key) ?? 0) + 1);
      return () => {
        const left = (rows.get(key) ?? 1) - 1;
        if (left > 0) rows.set(key, left);
        else rows.delete(key);
      };
    },
  };
}

const FormContext = createContext<ItemFormState>();

export function ItemFormProvider(props: ParentProps<{ state: ItemFormState }>) {
  return <FormContext value={props.state}>{props.children}</FormContext>;
}

export function useItemForm(): ItemFormState {
  const state = useContext(FormContext);
  if (!state) throw new Error("useItemForm(): there is no <ItemFormProvider> above");
  return state;
}
