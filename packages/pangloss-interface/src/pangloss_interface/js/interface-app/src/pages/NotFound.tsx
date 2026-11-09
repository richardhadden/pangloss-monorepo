import { PageTitle, useTranslations } from "@pangloss/interface-core";

export default function NotFound() {
  const { t } = useTranslations();
  return (
    <main>
      <PageTitle action={t("title_not_found", "Not found")} />
      <h1>{t("page_not_found", "Page not found")}</h1>
    </main>
  );
}
