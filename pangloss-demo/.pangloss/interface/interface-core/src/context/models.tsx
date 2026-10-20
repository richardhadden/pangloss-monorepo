import { createContext, useContext } from "solid-js";
import type { ParentProps } from "solid-js";
import { getModel } from "../schema";
import type { ModelDefinition, ModelDefinitions } from "../types";

const ModelsContext = createContext<ModelDefinitions>();

/** Makes the definitions of the models (generated from the project's) available below */
export function ModelsProvider(props: ParentProps<{ definitions: ModelDefinitions }>) {
  return <ModelsContext value={props.definitions}>{props.children}</ModelsContext>;
}

export function useModels(): ModelDefinitions {
  const definitions = useContext(ModelsContext);
  if (!definitions) {
    throw new Error("useModels(): there is no <ModelsProvider> above");
  }
  return definitions;
}

/** The definition of a model, or undefined if there is no such model */
export function useModel(name: string): ModelDefinition | undefined {
  return getModel(useModels(), name);
}
