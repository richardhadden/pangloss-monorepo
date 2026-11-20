"""The planted test of the class part (step 2.3 of implementation_docs/similarity-build-plan.md; the first one, of
2026-11-11, was lost with /tmp): does a class part beside the graph part bring the classes near a document's own
(parent, child, sibling) to the front, and leave what the graph says standing?

2,000 people in families, each with a craft. `Creation` → `CreationOfArtwork` → {`CreationOfPainting`,
`CreationOfSculpture`}, and `Creation` → `CreationOfBuilding`; each creation names a person of the matching craft,
`CreationOfArtwork` itself when the kind of work is not known. `Kinship` and `Mention` documents besides.

    uv run --no-project --with numpy --with scipy python notes/similarity-evaluation/hierarchy.py
"""

import numpy as np
from wrapper_walks import fastrp

PARENT = {
    "Creation": None,
    "CreationOfArtwork": "Creation",
    "CreationOfPainting": "CreationOfArtwork",
    "CreationOfSculpture": "CreationOfArtwork",
    "CreationOfBuilding": "Creation",
    "Kinship": None,
    "Mention": None,
}
CLASSES = list(PARENT)
K = 10


def chain(name):
    while name is not None:
        yield name
        name = PARENT[name]


def class_vectors(decay):
    vectors = np.zeros((len(CLASSES), len(CLASSES)))
    for name in CLASSES:
        for depth, above in enumerate(chain(name)):
            vectors[CLASSES.index(name), CLASSES.index(above)] = decay**depth if depth else 1.0
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def relation(a, b):
    """What the class b is to a: `near` (parent, child or sibling), `tree` (the same tree, further off), `unrelated`"""
    if PARENT[a] == b or PARENT[b] == a or (PARENT[a] is not None and PARENT[a] == PARENT[b]):
        return "near"
    return "tree" if list(chain(a))[-1] == list(chain(b))[-1] else "unrelated"


def data(seed):
    """Families of five share a trade (artists: painters and sculptors; or architects). A creation names its maker,
    a patron (anyone) and one of 60 places; the places and patrons, not the classes, are what the graph joins by"""
    rng = np.random.default_rng(seed)
    people, places = 2000, 60
    family = np.arange(people) // 5
    artists = rng.random(people // 5) < 0.67
    craft = np.where(artists[family], rng.choice(["painter", "sculptor"], people), "architect")
    home = rng.integers(0, places, people // 5)
    rows, classes, names = [], [], []

    def document(kind, who, place=None):
        number = people + places + len(classes)
        classes.append(kind)
        names.append(set(who))
        rows.extend((number, person, 1.0, "") for person in who)
        if place is not None:
            rows.append((number, people + place, 1.0, ""))

    for person in range(people):
        for _ in range(rng.integers(1, 4)):
            if craft[person] == "architect":
                kind = "CreationOfBuilding"
            elif rng.random() < 0.3:
                kind = "CreationOfArtwork"
            else:
                kind = "CreationOfPainting" if craft[person] == "painter" else "CreationOfSculpture"
            place = home[family[person]] if rng.random() < 0.7 else rng.integers(0, places)
            document(kind, [person, int(rng.integers(0, people))], int(place))
    for _ in range(1500):
        f = rng.integers(0, people // 5)
        document("Kinship", rng.choice(np.flatnonzero(family == f), 2, replace=False).tolist())
    for _ in range(1500):
        document("Mention", rng.choice(people, 2, replace=False).tolist(), int(rng.integers(0, places)))
    return people + places, rows, classes, names


def measure(graph, classes, names, decay, weight, carried=None):
    of_class = np.array([CLASSES.index(c) for c in classes])
    whole = graph / np.maximum(np.linalg.norm(graph, axis=1, keepdims=True), 1e-12)
    if weight:
        # (the square root: the cosine of the whole is then the graph's cosine plus `weight` times the class's, over
        # 1 + weight, which is what a profile's weight means)
        whole = np.hstack([whole, np.sqrt(weight) * class_vectors(decay)[of_class]])
    whole = whole / np.linalg.norm(whole, axis=1, keepdims=True)
    creations = [i for i, c in enumerate(classes) if c.startswith("Creation")]
    same = common = 0
    other = {"near": 0, "tree": 0, "unrelated": 0}
    for i in creations:
        scores = whole @ whole[i]
        scores[i] = -np.inf
        order = np.argsort(-scores)
        top = order[:K]
        same += sum(classes[j] == classes[i] for j in top)
        common += sum(bool(names[j] & names[i]) for j in top)
        others = [j for j in order if classes[j] != classes[i]][:K]
        for j in others:
            other[relation(classes[i], classes[j])] += 1
    total = len(creations) * K
    return [same / total, common / total] + [other[k] / total for k in ("near", "tree", "unrelated")]


def main():
    settings = [
        ("Graph only", 0.5, 0.0, False),
        ("Class part, no hierarchy (decay 0), weight 0.1", 0.0, 0.1, False),
        ("Hierarchy, decay 0.5, weight 0.1", 0.5, 0.1, False),
        ("Hierarchy, decay 0.5, weight 0.3", 0.5, 0.3, False),
        ("Hierarchy, decay 0.8, weight 0.1", 0.8, 0.1, False),
        ("Hierarchy, decay 0.8, weight 0.3", 0.8, 0.3, False),
    ]
    results = {name: [] for name, *_ in settings}
    for seed in (1, 2, 3):
        people, rows, classes, names = data(seed)
        vectors = fastrp(people + len(classes), rows, seed=seed)[people:]
        for name, decay, weight, _ in settings:
            results[name].append(measure(vectors, classes, names, decay, weight))
    print(f"{'':50} same class  person in common  other class: near   tree   unrelated")
    for name, runs in results.items():
        m = np.mean(runs, axis=0) * 100
        print(f"{name:50} {m[0]:8.1f}%  {m[1]:14.1f}%  {m[2]:16.1f}% {m[3]:5.1f}% {m[4]:8.1f}%")


main()
