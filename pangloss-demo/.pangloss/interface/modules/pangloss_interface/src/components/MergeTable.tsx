import {
  buttonClass,
  readableTime,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useTranslations,
} from "@pangloss/interface-core";
import { For } from "solid-js";
import { mergeHref } from "../api";
import type { MergeRecord } from "../api";
import { Pair, StateBadge } from "./parts";

/** Who last did something to a merge that is still to be said of it, and when */
export function lastOf(record: MergeRecord): { who: string; when: string | null | undefined } {
  if (record.state === "undone") return { who: record.undoneBy ?? "", when: record.undoneWhen };
  if (record.state === "rejected") return { who: record.rejectedBy ?? "", when: record.rejectedWhen };
  if (record.by) return { who: record.by, when: record.when };
  return { who: record.proposedBy ?? "", when: record.proposedWhen };
}

/** Merges as rows: the state, the two entities, who and when, and the way to the page of each */
export function MergeTable(props: { merges: MergeRecord[] }) {
  const { t, language } = useTranslations();
  return (
    <table class={tableClass} data-testid="merges-table">
      <thead>
        <tr class={tableHeadRowClass}>
          <th class={tableHeadCellClass} scope="col">
            {t("merges_state", "State")}
          </th>
          <th class={tableHeadCellClass} scope="col">
            {t("merges_pair", "Absorbed, and what it is merged into")}
          </th>
          <th class={tableHeadCellClass} scope="col">
            {t("merges_who", "By")}
          </th>
          <th class={tableHeadCellClass} scope="col">
            {t("merges_when", "When")}
          </th>
          <th class={tableHeadCellClass} scope="col" />
        </tr>
      </thead>
      <tbody>
        <For each={props.merges} keyed={(record) => record.id}>
          {(record) => (
            <tr class={tableRowClass} data-testid="merges-row" data-state={record().state}>
              <td class={tableCellClass}>
                <StateBadge record={record()} />
              </td>
              <td class={tableCellClass}>
                <Pair record={record()} />
              </td>
              <td class={tableCellClass}>{lastOf(record()).who}</td>
              <td class={[tableCellClass, "whitespace-nowrap"]}>{readableTime(lastOf(record()).when, language())}</td>
              <td class={[tableCellClass, "text-right"]}>
                <a class={buttonClass("quiet")} href={mergeHref(record().id)} data-testid="merges-open">
                  {t("merges_open", "Look at it")}
                </a>
              </td>
            </tr>
          )}
        </For>
      </tbody>
    </table>
  );
}
