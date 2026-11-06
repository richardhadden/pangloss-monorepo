import { useTranslations } from "@pangloss/interface-core";
import { Match, Switch } from "solid-js";
import type { Operation, VersionRecord } from "../api";

/** What a record of history says happened, in words */
export function useOpWords() {
  const { t } = useTranslations();
  return (record: Pick<VersionRecord, "op" | "restoredFrom">): string => {
    switch (record.op) {
      case "create":
        return t("history_op_create", "Created");
      case "update":
        return t("history_op_update", "Edited");
      case "restore":
        return record.restoredFrom
          ? t("history_op_restore_from", "Restored from version {version}", { version: String(record.restoredFrom) })
          : t("history_op_restore", "Restored");
      case "delete":
        return t("history_op_delete", "Deleted");
      case "undelete":
        return t("history_op_undelete", "Undeleted");
      case "baseline":
        return t("history_op_baseline", "Recorded as it was");
    }
  };
}

/** An icon of what happened (24-unit paths, as the console's) */
export function OpIcon(props: { op: Operation; class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["shrink-0 select-none fill-none stroke-current stroke-2", props.class ?? "size-3.5"]}
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <Switch>
        <Match when={props.op === "create"}>
          {/* (a new page) */}
          <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
          <path d="M14 3v5h5M12 11v6M9 14h6" />
        </Match>
        <Match when={props.op === "update"}>
          {/* (a pen) */}
          <path d="M4 20h4L19 9l-4-4L4 16v4z" />
        </Match>
        <Match when={props.op === "restore"}>
          {/* (an arrow turning back) */}
          <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
          <path d="M3 3v5h5" />
        </Match>
        <Match when={props.op === "delete"}>
          {/* (a bin) */}
          <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
        </Match>
        <Match when={props.op === "undelete"}>
          {/* (out of the bin) */}
          <path d="M6 10l1 10h10l1-10M12 18v-7M9 14l3-3 3 3M4 7h16" />
        </Match>
        <Match when={props.op === "baseline"}>
          {/* (a marker on a line: where history began) */}
          <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
        </Match>
      </Switch>
    </svg>
  );
}

/** The icon of history: a clock with an arrow going back round it */
export function HistoryIcon(props: { class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["select-none fill-none stroke-current stroke-2", props.class ?? "size-5"]}
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 1 0 2.6-6.4L3 8" />
      <path d="M3 3v5h5M12 7v5l3 2" />
    </svg>
  );
}
