# Interface module of `pangloss_calendar`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `pangloss_calendar` is in `INSTALLED_APPS`.
It adds three pages, and `interface_config.py` puts **Calendar** in the navigation bar:

- `/calendar` (`YearsPage`): the years of the span, each with how many dates meet it and its months as links.
- `/calendar/:calendar/:year/:month` (`MonthPage`, `MonthGrid`): the month as a calendar page, Monday first: dates as chips on
  their days, dates over several days as bars across the weeks (`lanes.ts` lays them in lanes), feasts named on their days.
- `/calendar/:calendar/:year/:month/:day` (`DayPage`, `DayView`): the day in both calendars, the feasts on it and how they come
  to be there, everything dated on it; logged in, attach a characterisation by name or take one away.

`src/api.ts` has the shapes and calls of `/api/calendar`; `src/days.ts` names days (`J1500-03-02`), builds addresses and says
dates and months in the language. The pages do no day arithmetic: both names of a day, and the days either side, come from the API.

Its tests run in a built project (`npx vitest run --root modules/pangloss_calendar` in `.pangloss/interface`); the e2e suite does
that. The user guide is [guide/calendar](../../../../../guide/calendar/README.md).
