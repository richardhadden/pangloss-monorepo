import { useBeforeLeave } from "@solidjs/router";

/**
 * What a page gives its form as `guardLeaving` (`ItemFormProps`): the router asks the form before the page is left, and
 * holds the navigation if the form says no (it then asks the person, and goes on with it, if told to, without asking
 * again)
 */
export function useLeaveGuard() {
  let guard: ((leave: () => void) => boolean) | undefined;
  useBeforeLeave((event) => {
    if (event.defaultPrevented || !guard) return;
    if (!guard(() => event.retry(true))) event.preventDefault();
  });
  return (given: (leave: () => void) => boolean) => {
    guard = given;
    return () => {
      if (guard === given) guard = undefined;
    };
  };
}
