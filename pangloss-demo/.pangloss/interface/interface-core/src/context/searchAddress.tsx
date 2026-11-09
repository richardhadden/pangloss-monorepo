import { createContext, useContext } from "solid-js";

export interface EverythingSearch {
  q: string;
  /** The name of the model it is narrowed to */
  type?: string;
}

/**
 * Where the search of `GlobalSearch` is kept, so that it can be linked to and comes back with the page: the application
 * gives the address (`?q=&type=`; the library knows nothing of the router). Without it the search is the component's own.
 */
export interface SearchAddress {
  q: () => string;
  type: () => string | undefined;
  set: (search: EverythingSearch) => void;
}

const SearchAddressContext = createContext<SearchAddress | null>(null);

export const SearchAddressProvider = SearchAddressContext;

export function useSearchAddress(): SearchAddress | null {
  return useContext(SearchAddressContext);
}
