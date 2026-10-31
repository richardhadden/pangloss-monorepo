import { Show } from "solid-js";
import { ApiError } from "../api";
import { useTranslations } from "../context";
import type { ErrorMessageProps } from "../types";

/**
 * What an error says to a person. An answer of the API is shown without its status number: a few
 * (not logged in, not allowed, the server failing) have words of their own, and for the rest the API's
 * own explanation is shown (it is English: the API is not multilingual). Anything else shows its message.
 */
export function ErrorMessage(props: ErrorMessageProps) {
  const { t } = useTranslations();
  const text = () => {
    const error = props.error;
    if (error instanceof ApiError) {
      if (error.status === 401)
        return t("error_unauthorised", "You need to log in to do this.");
      if (error.status === 403)
        return t("error_forbidden", "You are not allowed to do this.");
      if (error.status >= 500)
        return t(
          "error_server",
          "Something went wrong on the server. Please try again in a moment.",
        );
      return error.detail;
    }
    return error instanceof Error ? error.message : String(error);
  };
  return (
    <p role="alert" class="pg-error-message">
      <Show when={text()}>{text()}</Show>
    </p>
  );
}
