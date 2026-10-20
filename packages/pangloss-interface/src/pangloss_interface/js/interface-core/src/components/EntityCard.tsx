import { useComponent } from "../context";
import type { EntityCardProps } from "../types";

/** (a placeholder, to show how a component uses another that can be overridden) */
export function EntityCard(props: EntityCardProps) {
  const Button = useComponent("Button");
  return (
    <article class="pg-entity-card">
      <h2>{props.label}</h2>
      <p>{props.type}</p>
      <a href={`/${props.type}/${props.id}`}>
        <Button>Open</Button>
      </a>
    </article>
  );
}
