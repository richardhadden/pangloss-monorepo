import { Show } from "solid-js";
import { ApiError } from "../api";
import { useTranslations } from "../context";
import type { ErrorMessageProps } from "../types";

/**
 * What an error says to a person. An answer of the API is shown without its status number: a few
 * (not logged in, not allowed, the API not there, the server failing) have words of their own, and for the rest the API's
 * own explanation is shown (it is English: the API is not multilingual). Anything else shows its message.
 */
export function ErrorMessage(props: ErrorMessageProps) {
  const errorText = useErrorText();
  const text = () => errorText(props.error);
  return (
    <p role="alert" class="pg-error-message">
      <Show when={text()}>{text()}</Show>
    </p>
  );
}

/** What an error says to a person, as `ErrorMessage` shows it (for a toast) */
export function useErrorText(): (error: unknown) => string {
  const { t } = useTranslations();
  return (error) => {
    if (error instanceof ApiError) {
      if (error.status === 401)
        return t("error_unauthorised", "You need to log in to do this.");
      if (error.status === 403)
        return t("error_forbidden", "You are not allowed to do this.");
      // (the interface's own server says this when it cannot pass a request on: the API is not running, or is
      // not where the server was told it is. Its `detail` says which, for whoever runs the site)
      if (error.status === 502)
        return t(
          "error_api_unreachable",
          "The interface cannot reach the API. If you run this site: check that the API is running, and that the interface was told where it is.",
        );
      if (error.status >= 500)
        return t(
          "error_server",
          "Something went wrong on the server. Please try again in a moment.",
        );
      return error.detail;
    }
    return error instanceof Error ? error.message : String(error);
  };
}
