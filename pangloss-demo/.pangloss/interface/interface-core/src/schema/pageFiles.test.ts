import { expect, test } from "vitest";
import { pagesOf } from "./pageFiles";

const load = async () => ({ default: () => null });

test("index is the homepage, the others have an address from their name, in order", () => {
  const { home, pages } = pagesOf({
    "/p/pages/index.tsx": load,
    "/p/pages/Zebra.tsx": load,
    "/p/pages/Our-Team.tsx": load,
    "/p/pages/10-About.tsx": load,
    "/p/pages/_Draft.tsx": load,
  });
  expect(home).toBe(load);
  expect(pages.map((page) => page.slug)).toEqual(["about", "draft", "our-team", "zebra"]);
  expect(pages[0]).toMatchObject({ title: "About", slot: "page_about", hidden: false, order: 10 });
  expect(pages[1]).toMatchObject({ hidden: true });
  expect(pages[2]).toMatchObject({ title: "Our Team", slot: "page_our_team" });
});

test("no files, no pages", () => {
  expect(pagesOf({})).toEqual({ home: undefined, pages: [] });
});
