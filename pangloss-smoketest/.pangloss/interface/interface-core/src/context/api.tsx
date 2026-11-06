import { createContext, useContext } from "solid-js";
import type { ParentProps } from "solid-js";
import type { ApiClient } from "../api";

const ApiContext = createContext<ApiClient>();

export function ApiProvider(props: ParentProps<{ client: ApiClient }>) {
  return <ApiContext value={props.client}>{props.children}</ApiContext>;
}

export function useApi(): ApiClient {
  const client = useContext(ApiContext);
  if (!client) {
    throw new Error("useApi(): there is no <ApiProvider> above");
  }
  return client;
}
