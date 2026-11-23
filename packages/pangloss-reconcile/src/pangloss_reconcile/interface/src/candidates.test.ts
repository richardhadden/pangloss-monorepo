import { describe, expect, it } from "vitest";
import type { Candidate, CandidatesAnswer } from "./api";
import { barWidth, countShown, itemHref, partsText, probablyNewText, rowsOf, scoreText } from "./candidates";

const candidate = (id: string, score: number, changes: Partial<Candidate> = {}): Candidate => ({
  id,
  type: "Witness",
  label: id,
  score,
  scores: { name: score },
  shared: [],
  ...changes,
});

const answer = (candidates: Candidate[], changes: Partial<CandidatesAnswer> = {}): CandidatesAnswer => ({
  status: "ok",
  profile: "who",
  unknowns: [{ id: "m1", type: "Witness", label: "Karl", candidates }],
  ...changes,
});

describe("rowsOf", () => {
  it("gives the mention's candidates best first as the route gives them, at most five", () => {
    const all = ["a", "b", "c", "d", "e", "f"].map((id, n) => candidate(id, 0.9 - n * 0.05));
    expect(rowsOf(answer(all), "m1").map((row) => row.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(rowsOf(answer(all), "m1", 2).map((row) => row.id)).toEqual(["a", "b"]);
  });

  it("shows every candidate the route gives, whatever its score: the server cuts at its least score", () => {
    const rows = rowsOf(answer([candidate("a", 0.8), candidate("b", 0.3), candidate("c", 0.05)]), "m1");
    expect(rows.map((row) => row.id)).toEqual(["a", "b", "c"]);
  });

  it("gives nothing while the profile is being built, and shows those of a rebuild that is due", () => {
    expect(rowsOf(answer([candidate("a", 0.8)], { status: "pending" }), "m1")).toEqual([]);
    expect(rowsOf(answer([candidate("a", 0.8)], { status: "rebuild_due" }), "m1").map((row) => row.id)).toEqual(["a"]);
  });

  it("gives nothing for a mention the answer does not have, or that has no candidate", () => {
    expect(rowsOf(answer([candidate("a", 0.8)]), "m2")).toEqual([]);
    expect(rowsOf(answer([]), "m1")).toEqual([]);
    expect(rowsOf(answer([], { unknowns: [] }), "m1")).toEqual([]);
  });
});

describe("the figures", () => {
  it("draws a bar no shorter than nothing and no longer than the track", () => {
    expect(barWidth(0.5)).toBe("50%");
    expect(barWidth(-0.2)).toBe("0%");
    expect(barWidth(1.2)).toBe("100%");
  });

  it("writes a score with two decimals in the page's language", () => {
    expect(scoreText(0.9, "en")).toBe("0.90");
    expect(scoreText(0.456, "de")).toBe("0,46");
  });

  it("writes the score of each part, the highest first", () => {
    expect(partsText({ graph: 0.41, name: 0.95 }, "en")).toBe("name 0.95, graph 0.41");
    expect(partsText({ name: 0.5, graph: 0.5 }, "en")).toBe("graph 0.50, name 0.50");
    expect(partsText({}, "en")).toBe("");
  });

  it("writes shared with the parts, under the name it is given", () => {
    const named = (part: string) => (part === "shared" ? "named with" : part);
    expect(partsText({ graph: 0.41, name: 0.95, shared: 0.6 }, "en", named)).toBe(
      "name 0.95, named with 0.60, graph 0.41",
    );
    expect(partsText({ shared: 0.5 }, "de", () => "genannt mit")).toBe("genannt mit 0,50");
  });

  it("links an entity to its page", () => {
    expect(itemHref({ type: "Witness", id: "a b" })).toBe("/Witness/a%20b");
  });

  it("says a shared entity's count only above one", () => {
    expect(countShown(1)).toBe(false);
    expect(countShown(2)).toBe(true);
  });
});

describe("probablyNewText", () => {
  const unknown = (changes: object, candidates = [candidate("a", 0.4)]) =>
    answer([], { unknowns: [{ id: "m1", type: "Witness", label: "Karl", candidates, ...changes }] });

  it("gives the likelihood as a percentage in the page's language when the mention is probably none of these", () => {
    expect(probablyNewText(unknown({ new: 0.823, probablyNew: true }), "m1", "en")).toBe("82%");
    expect(probablyNewText(unknown({ new: 0.5, probablyNew: true }), "m1", "en")).toBe("50%");
    expect(probablyNewText(unknown({ new: 0.823, probablyNew: true }), "m1", "fr")).toMatch(/^82\s%$/u);
  });

  it("shows no line when the server did not say probablyNew, or gave no figure", () => {
    expect(probablyNewText(unknown({ new: 0.3, probablyNew: false }), "m1", "en")).toBeNull();
    expect(probablyNewText(unknown({}), "m1", "en")).toBeNull();
    // (a figure the server gave without the verdict, or a verdict without a figure: no line)
    expect(probablyNewText(unknown({ new: 0.9 }), "m1", "en")).toBeNull();
    expect(probablyNewText(unknown({ probablyNew: true }), "m1", "en")).toBeNull();
  });

  it("shows no line when there are no candidates to show, nor for another mention", () => {
    expect(probablyNewText(unknown({ new: 0.9, probablyNew: true }, []), "m1", "en")).toBeNull();
    expect(
      probablyNewText({ ...unknown({ new: 0.9, probablyNew: true }), status: "pending" }, "m1", "en"),
    ).toBeNull();
    expect(probablyNewText(unknown({ new: 0.9, probablyNew: true }), "m2", "en")).toBeNull();
  });
});
