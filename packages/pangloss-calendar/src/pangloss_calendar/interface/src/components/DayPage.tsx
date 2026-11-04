import { ApiError, useApi, useComponent, userIsLoggedIn, useSessionKey, useToasts, useTranslations } from "@pangloss/interface-core";
import { createMemo, createSignal, Errored, Loading, Show } from "solid-js";
import { attachToDay, detachFromDay, getDay } from "../api";
import type { CharacterisationOut } from "../api";
import { dayHref, nameFromParams, nameOf, refOf, sayDate } from "../days";
import type { DayName } from "../days";
import { Arrows, BadAddress, CalendarConsole, CalendarPage } from "./Chrome";
import { DayView } from "./DayView";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

function DayOf(props: { name: DayName }) {
  const api = useApi();
  const toasts = useToasts();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, language } = useTranslations();
  const loggedIn = createMemo(() => userIsLoggedIn());
  // (asked again after something is attached or taken away, and when someone logs in or out)
  const [version, setVersion] = createSignal(0);
  const session = useSessionKey();
  const report = createMemo(() => {
    version();
    session();
    return getDay(api, refOf(props.name), props.name.calendar);
  });
  const attach = async (characterisation: { id: string; label: string }) => {
    try {
      await attachToDay(api, characterisation.id, refOf(props.name));
      toasts?.show(t("calendar_attached_done", "{label} attached", { label: characterisation.label }), "success");
      setVersion((n) => n + 1);
    } catch (error) {
      toasts?.show(t("calendar_attach_refused", "Not attached: {reason}", { reason: reasonOf(error) }), "error");
    }
  };
  const detach = async (characterisation: CharacterisationOut) => {
    try {
      await detachFromDay(api, characterisation.id, refOf(props.name));
      toasts?.show(t("calendar_detached_done", "{label} detached", { label: characterisation.label }), "success");
      setVersion((n) => n + 1);
    } catch (error) {
      toasts?.show(t("calendar_detach_refused", "Not detached: {reason}", { reason: reasonOf(error) }), "error");
    }
  };
  return (
    <CalendarPage>
      <CalendarConsole
        calendar={props.name.calendar}
        label={sayDate(props.name, language(), t)}
        hrefOf={(calendar) => dayHref(nameOf(report().day, calendar))}
      />
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading
          fallback={
            <>
              <div class="mb-1 flex items-center gap-4">
                <Arrows
                  previousLabel={t("calendar_previous_day", "Previous day")}
                  nextLabel={t("calendar_next_day", "Next day")}
                />
                <h1 class="text-2xl font-semibold">{sayDate(props.name, language(), t)}</h1>
              </div>
              <p>{t("loading", "Loading…")}</p>
            </>
          }
        >
          <DayView
            report={report()}
            calendar={props.name.calendar}
            loggedIn={loggedIn()}
            onAttach={attach}
            onCreated={() => setVersion((n) => n + 1)}
            onDetach={detach}
          />
        </Loading>
      </Errored>
    </CalendarPage>
  );
}

/** A day of the calendar: /calendar/julian/1500/3/2 */
export default function DayPage(props: { params: Record<string, string | undefined> }) {
  const asked = () => nameFromParams(props.params);
  return (
    <Show when={asked()} fallback={<BadAddress />}>
      {(name) => <DayOf name={name()} />}
    </Show>
  );
}
