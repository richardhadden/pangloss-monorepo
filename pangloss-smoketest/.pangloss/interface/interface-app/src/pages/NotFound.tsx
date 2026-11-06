import { useTranslations } from "@pangloss/interface-core";
import { Title } from "@solidjs/meta";

export default function NotFound() {
  const { t } = useTranslations();
  return (
    <main>
      <Title>{t("title_not_found", "Not found - Pangloss")}</Title>
      <h1>{t("page_not_found", "Page not found")}</h1>
    </main>
  );
}
