// The pages of the project, from the files of `<project>/pages/`, and the console that links them. Compiled where they
// are, so an edit is seen at once. (The alias is in vite.config.ts.)
import { ConsoleButton, pagesOf, useConsoleMount, useTranslations } from "@pangloss/interface-core";
import type { PageLoader } from "@pangloss/interface-core";
import { Portal } from "@solidjs/web";
import { For, lazy, onSettled, Show } from "solid-js";

export const { home: projectHome, pages: projectPages } = pagesOf(
  import.meta.glob("@project-pages/*.tsx") as Record<string, PageLoader>,
);

const linked = projectPages.filter((page) => !page.hidden);

/** Links to the homepage and the pages, in the console. A project with no pages has no console here. */
export function PagesConsole(props: { current?: string }) {
  const { mount, register } = useConsoleMount();
  const { t } = useTranslations();
  onSettled(() => (linked.length > 0 ? register() : undefined));
  return (
    <Show when={linked.length > 0 && mount()}>
      {(element) => (
        <Portal mount={element() as HTMLElement}>
          <nav aria-label={t("pages", "Pages")} class="flex h-full flex-1 items-center justify-end">
            <ConsoleButton text label={t("home", "Home")} href="/" pressed={props.current === undefined} />
            <For each={linked}>
              {(page) => (
                <ConsoleButton
                  text
                  label={t(page.slot, page.title)}
                  href={`/${page.slug}`}
                  pressed={props.current === page.slug}
                />
              )}
            </For>
          </nav>
        </Portal>
      )}
    </Show>
  );
}

/**
 * A page with the console of the pages. `slug` is undefined for the homepage. (The page itself is what is `lazy`, as
 * it came from its file: hydration finds its code by what the file's module says of itself.)
 */
export function pageComponent(load: PageLoader, slug?: string) {
  const Page = lazy(load);
  return () => (
    <>
      <PagesConsole current={slug} />
      <Page />
    </>
  );
}
