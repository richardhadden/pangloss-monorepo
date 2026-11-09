import { Show } from "solid-js";
import { ConsoleButton, useIncomingView, useTranslations } from "@pangloss/interface-core";
import type { ConsoleActionProps } from "@pangloss/interface-core";

/** The name of the view it chooses (`incomingViews.ByDate` of this module) */
export const BY_DATE = "pangloss_dates:ByDate";

/**
 * A button in the console of an item's page that sorts what refers to the item by date (the view `ByDate`) or, pressed
 * again, groups it by the field it is in. Shown only while the page has something that can have a date.
 */
export default function SortByDate(props: ConsoleActionProps) {
  const { t } = useTranslations();
  const incoming = useIncomingView();
  const pressed = () => incoming.chosen() === BY_DATE;
  return (
    <Show when={props.page === "item" && incoming.offered(BY_DATE)}>
      <ConsoleButton
        label={t("incoming_sort_by_date", "Sort by date")}
        pressed={pressed()}
        onClick={() => incoming.choose(pressed() ? undefined : BY_DATE)}
      >
        {/* (a calendar) */}
        <svg
          viewBox="0 0 24 24"
          class="size-5 select-none fill-none stroke-current stroke-[1.5]"
          stroke-linecap="square"
          aria-hidden="true"
        >
          <path d="M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM4 10.5h16M8.5 3.5v4M15.5 3.5v4" />
        </svg>
      </ConsoleButton>
    </Show>
  );
}
