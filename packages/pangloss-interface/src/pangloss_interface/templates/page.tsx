import { PageTitle } from "@pangloss/interface-core";

export default function {{component}}() {
  return (
    <main class="mx-auto max-w-3xl px-6 py-12">
      <PageTitle section="{{title}}" />
      <h1 class="text-4xl font-semibold tracking-tight text-slate-800">{{title}}</h1>
    </main>
  );
}
