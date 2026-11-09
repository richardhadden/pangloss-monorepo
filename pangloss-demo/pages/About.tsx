import { PageTitle } from "@pangloss/interface-core";

const linkClass = "font-medium text-slate-900 underline underline-offset-2 hover:text-slate-600";

export default function About() {
  return (
    <main class="mx-auto max-w-3xl px-6 py-12">
      <PageTitle section="About" />
      <h1 class="text-4xl font-semibold tracking-tight text-slate-800">About</h1>

      <div class="mt-8 flex flex-col gap-5 leading-relaxed text-slate-700">
        <p>
          This is a demonstration of Pangloss, a framework for research databases about people, sources, statements,
          events and places: data that fits a graph better than a table. Its data model is declared once, as Python
          classes, and the storage, the API and this interface are all made from it.
        </p>
        <p>
          The demonstration is a factoid prosopography. A{" "}
          <a href="/Factoid" class={linkClass}>
            factoid
          </a>{" "}
          records what one source says, as a set of statements about{" "}
          <a href="/Person" class={linkClass}>
            people
          </a>
          ,{" "}
          <a href="/Place" class={linkClass}>
            places
          </a>{" "}
          and{" "}
          <a href="/Group" class={linkClass}>
            groups
          </a>
          . A statement can sit inside others: an order to carry out a transfer holds the transfer that was ordered,
          marked as something wished for and not necessarily done.
        </p>

        <h2 class="mt-4 text-xl font-semibold text-slate-800">About the data</h2>
        <p>
          The data here exists to show what the interface does. Historical names appear in it, but the records were
          written for this demonstration, and many of the people are invented. Please do not cite any of it.
        </p>
      </div>
    </main>
  );
}
