import { HydrationScript } from "@solidjs/web";
import type { ParentProps } from "solid-js";

// The HTML shell: it renders the whole document, and no client code of its own
export default function Document(props: ParentProps) {
  return (
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Pangloss</title>
        <HydrationScript />
      </head>
      <body>{props.children}</body>
    </html>
  );
}
