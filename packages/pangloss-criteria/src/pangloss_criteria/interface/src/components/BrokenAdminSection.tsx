import { useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import { createMemo, Errored, Loading } from "solid-js";
import { brokenDescriptions } from "../api";

/** How many descriptions are out of date (one answer of the route, the count alone) */
function Count() {
  const api = useApi();
  const { t } = useTranslations();
  const found = createMemo(() => brokenDescriptions(api, 1, 1));
  const said = () => {
    const count = found().count;
    if (count === 0) return t("criteria_broken_none", "No description is out of date.");
    return count === 1
      ? t("criteria_broken_one", "1 description is out of date.")
      : t("criteria_broken_many", "{count} descriptions are out of date.", { count: String(count) });
  };
  return (
    <p class="text-sm text-slate-700" data-testid="admin-criteria-broken-count">
      {said()}
    </p>
  );
}

/**
 * On `/admin` (`slots.admin`): how many descriptions are out of date after a migration, and the link to the page
 * that lists them (`/criteria/broken`)
 */
export default function BrokenAdminSection() {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  return (
    <section data-testid="admin-criteria-broken">
      <div class="mb-3 flex items-baseline gap-4">
        <h2 class="text-sm font-semibold uppercase">{t("criteria_broken_title", "Descriptions out of date")}</h2>
        <a class="text-xs font-semibold text-slate-600 uppercase hover:underline" href="/criteria/broken">
          {t("criteria_broken_all", "List them")}
        </a>
      </div>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
          <Count />
        </Loading>
      </Errored>
    </section>
  );
}
