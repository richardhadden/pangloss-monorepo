import { defineModule } from "@pangloss/interface-core";

// The interface of the calendar: the years of the project's span (/calendar), a month as a calendar page
// (/calendar/julian/1500/3), and a day (/calendar/julian/1500/3/2), each read in the Julian or the Gregorian
// calendar. The navigation bar links to the years: pangloss_calendar/interface_config.py.
export default defineModule({
  name: "pangloss_calendar",
  requires: [],
  components: {
    YearsPage: () => import("./components/YearsPage"),
    MonthPage: () => import("./components/MonthPage"),
    DayPage: () => import("./components/DayPage"),
  },
  routes: [
    { path: "/calendar", component: "YearsPage" },
    { path: "/calendar/:calendar/:year/:month", component: "MonthPage" },
    { path: "/calendar/:calendar/:year/:month/:day", component: "DayPage" },
  ],
});
