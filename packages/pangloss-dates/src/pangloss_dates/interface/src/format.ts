type Data = Record<string, unknown>;

export const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

const isData = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const num = (value: unknown) => (typeof value === "number" ? value : undefined);

/** 25 December 800; December 800; 800 */
function exact(date: Data): string {
  const month = num(date.month);
  const day = num(date.day);
  return [
    day,
    month !== undefined ? (MONTHS[month - 1] ?? month) : undefined,
    num(date.year),
  ]
    .filter((part) => part !== undefined)
    .join(" ");
}

function recurrence(date: Data): string {
  const weekdays = (Array.isArray(date.weekdays) ? date.weekdays : []).map(
    (w) => WEEKDAYS[w as number] ?? w,
  );
  const every =
    Array.isArray(date.weekdays) && weekdays.length > 0
      ? weekdays.join(", ")
      : String(date.frequency ?? "");
  return `every ${num(date.interval) && date.interval !== 1 ? `${date.interval} ` : ""}${every}`.trim();
}

/**
 * A date as a person would say it, from the JSON of any of the date models of `pangloss_dates`
 * (`undefined` for something that is not a date it knows). The calendar is named only if it is not the
 * Gregorian, and what the source said (`sourceText`) follows in quotes.
 */
export function formatDate(date: unknown): string | undefined {
  return say(date, true);
}

// (the ends of a period or a range are in its calendar: they do not say it again)
function say(date: unknown, outer: boolean): string | undefined {
  if (!isData(date)) return undefined;
  let text: string | undefined;
  switch (date.type) {
    case "ExactDate":
      text = exact(date);
      break;
    case "EDTFDate":
      text = typeof date.edtf === "string" ? date.edtf : undefined;
      break;
    case "DateRange":
      text = `${say(date.earliest, false)} to ${say(date.latest, false)}`;
      break;
    case "OngoingDate":
      text = "ongoing";
      break;
    case "UnknownDate":
      text = "unknown";
      break;
    case "Period":
      text = `${say(date.start, false)} – ${say(date.end, false)}`;
      break;
    case "Recurrence":
      text = `${recurrence(date)}, ${say(date.start, false)} – ${say(date.end, false)}`;
      break;
    default:
      return undefined;
  }
  if (text === undefined) return undefined;
  if (
    typeof date.calendar === "string" &&
    date.calendar !== "gregorian" &&
    outer
  ) {
    text += ` (${date.calendar})`;
  }
  if (outer && typeof date.sourceText === "string" && date.sourceText)
    text += ` “${date.sourceText}”`;
  return text;
}
