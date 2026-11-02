import { createContext, createStore, snapshot, useContext } from "solid-js";
import type { ParentProps } from "solid-js";
import { getAt, removeAt, setAt } from "../schema";
import type { FormData, Path } from "../schema";

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
}

/** Starts from a copy of `initial` */
export function createItemFormState(initial: FormData): ItemFormState {
  const [data, setData] = createStore<FormData>(structuredClone(initial));
  return {
    get: (path) => getAt(data, path),
    set: (path, value) =>
      setData((draft) => {
        setAt(draft, path, value);
      }),
    remove: (path) =>
      setData((draft) => {
        removeAt(draft, path);
      }),
    plain: () => snapshot(data) as FormData,
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
