import { HydrationScript } from "@solidjs/web";
import type { ParentProps } from "solid-js";
import "./styles.css";

// The P of Pangloss as nodes and edges, the outermost node of its bowl a sun. In the page, so that nothing has to serve it
const FAVICON_GRAPH = `data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
    `<rect width="32" height="32" rx="5" fill="#1e293b"/>` +
    `<path d="M9 6V26M9 6H15.5L21 12.5 15.5 19H9" fill="none" stroke="#e2e8f0" stroke-width="2"/>` +
    `<g fill="#e2e8f0"><circle cx="9" cy="6" r="3"/><circle cx="15.5" cy="6" r="2.25"/><circle cx="15.5" cy="19" r="2.25"/>` +
    `<circle cx="9" cy="19" r="2.25"/><circle cx="9" cy="26" r="3"/></g>` +
    `<circle cx="21" cy="12.5" r="3.5" fill="#fbbf24"/>` +
    `<path d="M26.5 12.5H29.5M25.8 9.7L28.4 8.2M25.8 15.3L28.4 16.8M23 7.3L24.5 4.7M23 17.7L24.5 20.3" fill="none" stroke="#fbbf24" stroke-width="1.25"/>` +
    `</svg>`,
)}`;

// Voltaire in profile, in two colours. (`href` below says which of the two is in use)
const FAVICON_VOLTAIRE = `data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="5" fill="#1e293b"/><path d="M15 4.5C19.5 3.5 22.5 6 23 10.5L22.6 12 27.5 18.2C27.8 19 26.5 19.4 24.2 19.3L24.8 21 23.2 22.1 24.2 23.2 23 24.4C24 26.5 22.8 28.4 20.2 28 17.8 27.7 16 26.8 15 25.6L15 32H10.5L12 21C13.5 15 13 9 15 4.5Z" fill="#fbbf24"/><path d="M13.2 3.2C8.5 3 5 6.2 5.6 9.5 3.4 10.8 3.2 13.6 5 15 3 16.6 3 19.4 5 20.6 3.4 22.4 4.2 25.4 7 25.8 7.6 27.2 9.2 27.4 10 26.8L11 20.5C12.2 14.5 11.6 8.5 13.2 3.2Z" fill="#fbbf24"/><path d="M18.2 12.4Q20.2 10.8 22.2 12.2" fill="none" stroke="#1e293b" stroke-width="1.4"/><path d="M24.4 21.1Q21.8 21.6 20 19.6" fill="none" stroke="#1e293b" stroke-width="1"/></svg>`,
)}`;

// The HTML shell: it renders the whole document, and no client code of its own
export default function Document(props: ParentProps) {
  return (
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Pangloss</title>
        <link rel="icon" type="image/svg+xml" href={FAVICON_VOLTAIRE} />
        <HydrationScript />
      </head>
      <body>{props.children}</body>
    </html>
  );
}
