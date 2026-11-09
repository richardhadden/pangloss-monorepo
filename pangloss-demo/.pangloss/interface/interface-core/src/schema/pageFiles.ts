// What the files of `<project>/pages/` are (docs/homepage-and-pages.md). `pangloss_interface/pages.py` reads the names the same way.
import type { Component } from "solid-js";

export type PageLoader = () => Promise<{ default: Component }>;

export interface ProjectPage {
  /** The address: `/<slug>` */
  slug: string;
  /** What the link says, if the translations have no `page_<slug>` */
  title: string;
  /** The translation slot of the link */
  slot: string;
  /** `_Name.tsx`: it has an address, and no link */
  hidden: boolean;
  /** `10-Name.tsx`: links are ordered by this, then by title */
  order: number;
  load: PageLoader;
}

export function pagesOf(files: Record<string, PageLoader>): { home?: PageLoader; pages: ProjectPage[] } {
  let home: PageLoader | undefined;
  const pages: ProjectPage[] = [];
  for (const [path, load] of Object.entries(files)) {
    const file = path.slice(path.lastIndexOf("/") + 1).replace(/\.tsx$/, "");
    if (file === "index") {
      home = load;
      continue;
    }
    const hidden = file.startsWith("_");
    const numbered = /^(\d+)[-_](.+)$/.exec(hidden ? file.slice(1) : file);
    const name = numbered ? numbered[2]! : hidden ? file.slice(1) : file;
    const slug = name.toLowerCase().replaceAll("_", "-");
    pages.push({
      slug,
      title: name.replace(/[-_]+/g, " "),
      slot: `page_${slug.replaceAll("-", "_")}`,
      hidden,
      order: numbered ? Number(numbered[1]) : Number.MAX_SAFE_INTEGER,
      load,
    });
  }
  pages.sort((a, b) => a.order - b.order || a.title.localeCompare(b.title));
  return { home, pages };
}
