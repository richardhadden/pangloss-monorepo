import { httpStatus } from "@solidjs/web";
import { useTranslations } from "../context";
import { PageTitle } from "./PageTitle";

/** The page for an address where there is nothing: also for a page that someone must not know is there */
export function NotFound() {
  const { t } = useTranslations();
  httpStatus(404);
  return (
    <main>
      <PageTitle action={t("title_not_found", "Not found")} />
      <h1>{t("page_not_found", "Page not found")}</h1>
    </main>
  );
}
