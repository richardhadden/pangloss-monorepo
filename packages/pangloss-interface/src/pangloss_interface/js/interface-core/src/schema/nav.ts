import type { ModelDefinitions } from "../types";
import { modelHierarchy } from "./hierarchy";

export interface NavEntry {
  label: string;
  /** The model it is the list of, if a model's (its name is then translated, unless an app gave a label) */
  model?: string;
  href: string;
  /** How many steps the text is moved in (the types of the hierarchy; a type placed elsewhere is not) */
  depth: number;
  external: boolean;
  requiresLogin: boolean;
}

export interface NavSection {
  title: string;
  entries: NavEntry[];
}

const KIND_SECTIONS = [
  { title: "Entities", kind: "Entity" },
  { title: "Documents", kind: "Document" },
] as const;
const LINKS_SECTION = "Links";

/**
 * The sections of the navigation bar: the Entities and the Documents in the order of the type
 * hierarchy, as ever, then what the apps' `InterfaceConfig`s (`definitions.nav`) change: a type
 * moved to another section, given a label or an order, or hidden; and their other links. A type
 * is listed under, in order of precedence: the section an app's `NavModel` gives it, the section
 * its `InterfaceMeta(nav_section=...)` gives it (its parents' too), and Entities or Documents by its
 * kind. A type is indented below its parent only when the parent is in the same section. In a
 * section, entries with an `order` come first, by it; the rest follow in the order they were met
 * (the hierarchy, then the links). A section with nothing in it is left out.
 */
export function navSections(definitions: ModelDefinitions): NavSection[] {
  const nav = definitions.nav ?? {
    sections: KIND_SECTIONS.map((s) => s.title),
    models: {},
    links: [],
  };
  const titles = [...nav.sections];
  const found = new Map<string, { entry: NavEntry; order: number | null }[]>();
  const add = (section: string, entry: NavEntry, order: number | null) => {
    if (!titles.includes(section)) titles.push(section);
    found.set(section, [...(found.get(section) ?? []), { entry, order }]);
  };
  // (where each type was put, so that a type is indented under its parent only if that is in the same section)
  const put = new Map<string, { section: string; depth: number }>();
  for (const { title, kind } of KIND_SECTIONS) {
    for (const { model } of modelHierarchy(definitions, kind)) {
      const placement = Object.hasOwn(nav.models, model.name)
        ? nav.models[model.name]!
        : undefined;
      if (placement?.hidden) continue;
      // (an abstract type with no concrete type below it has nothing to list)
      if (model.abstract && model.concreteTypes.length === 0) continue;
      const section =
        placement?.section ?? model.interfaceMeta?.navSection ?? title;
      const parent = model.parent === null ? undefined : put.get(model.parent);
      const depth = parent?.section === section ? parent.depth + 1 : 0;
      put.set(model.name, { section, depth });
      add(
        section,
        {
          label: placement?.label ?? model.name,
          ...(placement?.label ? {} : { model: model.name }),
          href: `/${model.name}`,
          depth,
          external: false,
          requiresLogin: false,
        },
        placement?.order ?? null,
      );
    }
  }
  for (const link of nav.links) {
    add(
      link.section ?? LINKS_SECTION,
      {
        label: link.label,
        href: link.href,
        depth: 0,
        external: link.external,
        requiresLogin: link.requiresLogin,
      },
      link.order,
    );
  }
  return titles.flatMap((title) => {
    const entries = found.get(title) ?? [];
    if (entries.length === 0) return [];
    const ordered = entries
      .filter((e) => e.order !== null)
      .sort((a, b) => a.order! - b.order!);
    const rest = entries.filter((e) => e.order === null);
    return [{ title, entries: [...ordered, ...rest].map((e) => e.entry) }];
  });
}
