import { headModels, useModels } from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";
import { For } from "solid-js";

// What there is to show is from the definitions of the models of the project
export default function Home() {
  const models = headModels(useModels());
  return (
    <main>
      <Title>Pangloss</Title>
      <h1>Pangloss Yo!</h1>
      <ul>
        <For each={models}>
          {(model) => (
            <li>
              <a href={`/${model.name}`}>{model.name}</a> ({model.kind})
            </li>
          )}
        </For>
      </ul>
    </main>
  );
}
