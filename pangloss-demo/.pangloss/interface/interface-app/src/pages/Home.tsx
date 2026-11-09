import { GlobalSearch, PageTitle, readableName, useModels } from "@pangloss/interface-core";

// The homepage: the name of the project, and a box that searches everything
export default function Home() {
  const definitions = useModels();
  return (
    <main class="mx-auto flex max-w-4xl flex-col gap-10 px-6 pt-24 pb-12">
      <PageTitle />
      <h1 class="text-center text-7xl font-semibold tracking-tight wrap-break-word text-slate-800">
        {readableName(definitions.projectName ?? "Pangloss")}
      </h1>
      <GlobalSearch />
    </main>
  );
}
