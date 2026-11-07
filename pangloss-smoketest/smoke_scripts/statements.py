"""Invented statements of every kind, as JSON payloads for `Factoid.Create` (over the REST API)"""

import fake
from fake import R

GROUPS = ["Family", "Guild", "ReligiousOrder", "Army", "TradingCompany", "University", "Monastery", "Court"]
PLACES = ["Settlement", "Settlement", "Settlement", "Region", "Building", "Place"]


class Pool:
    def __init__(self, entities: dict[str, list[str]], sources: list[dict]):
        self.e = entities
        self.sources = sources

    def ref(self, kind: str) -> dict:
        return {"type": kind, "id": R.choice(self.e[kind])}

    def person(self) -> dict:
        return self.ref("Person")

    def people(self, lo: int, hi: int) -> list[dict]:
        return [self.person() for _ in range(R.randint(lo, hi))]

    def group(self) -> dict:
        return self.ref(R.choice(GROUPS))

    def agent(self) -> dict:
        return self.person() if R.random() < 0.75 else self.group()

    def agents(self, lo: int, hi: int) -> list[dict]:
        return [self.agent() for _ in range(R.randint(lo, hi))]

    def place(self) -> dict:
        return self.ref(R.choice(PLACES))

    def places(self) -> list[dict]:
        return [self.place() for _ in range(R.choices([0, 1, 2], [3, 6, 1])[0])]

    def via(self, ref: dict) -> dict:
        return {**ref, "edge_properties": {"level": R.randint(1, 5)}}

    def identified(self) -> dict:
        """A name in the source that could be one of two or three people"""
        n = R.randint(2, 3)
        shares = [100 // n] * n
        shares[0] += 100 - sum(shares)
        return {
            "type": "Identification",
            "identified_by": R.choice(fake.FIRST_M),
            "target": [{
                "type": "WeightedAlternative",
                "alternatives": [{**self.person(), "edge_properties": {"percent": s}} for s in shares],
            }],
        }

    def agent_or_identified(self) -> dict:
        return self.identified() if R.random() < 0.08 else self.agent()

    def source(self) -> dict:
        page = R.choice([str(R.randint(1, 600)), f"fol. {R.randint(1, 300)}{R.choice('rv')}", f"no. {R.randint(1, 900)}"])
        return {"type": "AtPage", "page": page, "target": [R.choice(self.sources)]}


def base(kind: str, label: str, text: str) -> dict:
    return {"type": kind, "label": label[:200], "text": text}


def make(pool: Pool, kind: str) -> dict:
    p = pool
    who = p.person()
    lbl = f"{kind} ({R.randint(1, 10**6)})"
    ev = lambda: {"date": fake.single_date(), "places": p.places()}  # noqa: E731
    per = lambda: {"date": fake.period(), "places": p.places()}  # noqa: E731
    anyd = lambda: {"date": fake.any_date(), "places": p.places()}  # noqa: E731
    makers = {
        # single dates
        "Birth": lambda: {**ev(), "child": who, "parents": p.people(0, 2)},
        "Baptism": lambda: {**ev(), "baptised": who, "godparents": p.people(0, 3)},
        "Death": lambda: {**ev(), "deceased": who, "cause": R.choice([None, "plague", "fever", "in battle", "old age"])},
        "Burial": lambda: {**ev(), "buried": who},
        "Marriage": lambda: {**ev(), "spouses": p.people(2, 2), "dowry": str(R.randint(100, 20000))},
        "Betrothal": lambda: {**ev(), "betrothed": p.people(2, 2)},
        "Ordination": lambda: {**ev(), "ordained": who, "ordained_by": p.people(0, 1)},
        "Coronation": lambda: {**ev(), "crowned": who, "office": p.ref("Office")},
        "Knighting": lambda: {**ev(), "knighted": who, "knighted_by": p.people(0, 1)},
        "Ennoblement": lambda: {**ev(), "ennobled": p.agent(), "has_type": [p.ref("TitleType")]},
        "Graduation": lambda: {**ev(), "graduate": who, "university": p.ref("University"), "degree": R.choice(fake.DEGREES)},
        "Matriculation": lambda: {**ev(), "student": who, "university": p.ref("University")},
        "Execution": lambda: {**ev(), "executed": who},
        "Election": lambda: {**ev(), "elected": who, "office": p.ref("Office"), "votes": R.randint(3, 400)},
        "Appointment": lambda: {**ev(), "appointee": who, "appointed_by": p.agents(0, 2), "office": p.ref("Office")},
        "Dismissal": lambda: {**ev(), "dismissed": who, "office": p.ref("Office")},
        "Conversion": lambda: {**ev(), "convert": who, "from_faith": R.choice(fake.FAITHS), "to_faith": R.choice(fake.FAITHS)},
        "Excommunication": lambda: {**ev(), "excommunicated": p.agent()},
        "Founding": lambda: {**ev(), "founder": p.via(p.agent()), "founded": p.group()},
        "Construction": lambda: {**ev(), "builder": p.agents(1, 3), "building": p.ref("Building")},
        "Destruction": lambda: {**ev(), "destroyed": p.ref("Building"), "destroyed_by": p.agents(0, 2)},
        "Shipwreck": lambda: {**ev(), "involves": p.people(0, 3), "ship": p.ref("Ship")},
        "Canonisation": lambda: {**ev(), "saint": who},
        # periods
        "OfficeHolding": lambda: {**per(), "holder": p.via(who), "office": p.ref("Office")},
        "Residence": lambda: {**per(), "resident": p.agent()},
        "Apprenticeship": lambda: {**per(), "apprentice": who, "master": p.agents(1, 1), "guild": [p.ref("Guild")]},
        "Membership": lambda: {**per(), "member": p.agent_or_identified(), "group": p.group()},
        "Employment": lambda: {**per(), "employee": who, "employer": p.agents(1, 1), "wage": str(R.randint(5, 500))},
        "Imprisonment": lambda: {**per(), "prisoner": who},
        "Exile": lambda: {**per(), "exiled": p.agent()},
        "Reign": lambda: {**per(), "ruler": who, "realm": p.ref("Region")},
        "StudyAt": lambda: {**per(), "student": who, "university": p.ref("University")},
        "Siege": lambda: {**per(), "besiegers": [p.ref("Army")], "besieged": p.ref("Settlement")},
        "Pilgrimage": lambda: {**per(), "pilgrim": who, "destination": p.place()},
        # any date
        "Meeting": lambda: {**anyd(), "involves": [], "participants": [
            {"type": "InRole", "role": R.choice(["leader", "witness", "participant", "messenger", "host"]), "target": [p.agent()]}
            for _ in range(R.randint(2, 5))]},
        "Letter": lambda: {**anyd(), "sender": p.agent(), "recipient": p.agent(), "language": [p.ref("Language")]},
        "Gift": lambda: {**anyd(), "item": R.choice(fake.COMMODITIES), "quantity": str(R.randint(1, 100)),
                         "given_by": p.agent_or_identified(), "given_to": p.agent_or_identified()},
        "Sale": lambda: {**anyd(), "seller": p.agent(), "buyer": p.agent(), "commodity": [p.ref("Commodity")],
                         "price": f"{R.randint(1, 9000)}.{R.randint(0, 99):02}", "currency": p.ref("Currency")},
        "Loan": lambda: {**anyd(), "lender": p.agent(), "borrower": p.agent(), "amount": str(R.randint(10, 100000)),
                         "currency": p.ref("Currency"), "interest_percent": round(R.uniform(2, 30), 1)},
        "Payment": lambda: {**anyd(), "payer": p.agent(), "payee": p.agent(), "amount": str(R.randint(1, 5000)),
                            "currency": p.ref("Currency")},
        "Commission": lambda: {**anyd(), "patron": p.agent(), "artist": who,
                               "artwork": p.ref(R.choice(["Painting", "Sculpture", "Artwork"]))},
        "CreationOfPhysicalObject": lambda: {**anyd(), "created_by": who,
                                             "object_created": p.ref(R.choice(["PhysicalObject", "Ship", "Manuscript"]))},
        "CreationOfArtwork": lambda: {**anyd(), "created_by": who, "artwork_created": p.ref(R.choice(["Painting", "Sculpture"]))},
        "Printing": lambda: {**anyd(), "printer": p.agent(), "book": p.ref("Book"), "copies": R.randint(100, 1500)},
        "Authorship": lambda: {**anyd(), "author": who, "work": p.ref(R.choice(["Book", "Manuscript"]))},
        "Translation": lambda: {**anyd(), "translator": who, "work": p.ref(R.choice(["Book", "Manuscript"])),
                                "into": p.ref("Language")},
        "Battle": lambda: {**anyd(), "sides": [p.ref("Army"), p.ref("Army")], "victor": [p.ref("Army")][: R.randint(0, 1)],
                           "casualties": R.randint(10, 20000)},
        "Treaty": lambda: {**anyd(), "parties": p.agents(2, 4), "terms": "peace and free passage of merchants"},
        "Voyage": lambda: {**anyd(), "ship": p.ref("Ship"), "captain": p.people(0, 1), "from_place": p.ref("Settlement"),
                           "to_place": p.ref("Settlement"), "cargo": [p.ref("Commodity") for _ in range(R.randint(0, 3))]},
        "Lawsuit": lambda: {**anyd(), "plaintiff": p.agent(), "defendant": p.agent(), "court": [p.ref("Court")],
                            "matter": R.choice(fake.CHARGES)},
        "Accusation": lambda: {**anyd(), "accuser": p.agent(), "accused": p.agent(), "charge": R.choice(fake.CHARGES)},
        "Pardon": lambda: {**anyd(), "pardoned": who, "pardoned_by": p.people(0, 1)},
        "Petition": lambda: {**anyd(), "petitioner": p.agent(), "petitioned": p.agent(), "request": "relief from taxes"},
        "Sermon": lambda: {**anyd(), "preacher": who, "theme": R.choice(fake.THEMES)},
        "Visit": lambda: {**anyd(), "visitor": p.agent(), "host": p.agents(1, 2)},
        "Inheritance": lambda: {**anyd(), "heir": who, "from_deceased": p.person(), "what": R.choice(["a house", "the shop", "lands"])},
        "Donation": lambda: {**anyd(), "donor": p.agent(), "recipient_institution": p.ref(R.choice(["Monastery", "University", "ReligiousOrder"])),
                             "amount": str(R.randint(1, 3000))},
        "Order": lambda: order(p),
        # deep nesting (2026-11-07)
        "Witnessing": lambda: {**anyd(), "presided_by": p.agent(), "witnesses": [witness(p) for _ in range(R.randint(1, 4))]},
        "SealedLetter": lambda: {**anyd(), "sealed_by": p.agent(), "seal": seal()},
        # undated
        "Kinship": lambda: {"person": who, "relative": p.person(), "kinship_kind": R.choice(
            ["parent", "sibling", "cousin", "uncle_or_aunt", "grandparent", "godparent"])},
        "PhysicalDescription": lambda: {"described": who, "description": R.choice(fake.DESCRIPTIONS)},
        "Characterisation": lambda: {"characterised": p.agent(), "trait": R.choice(fake.TRAITS)},
        "NameVariant": lambda: {"named": p.agent(), "name": {"value": f"{R.choice(fake.FIRST_M)} {R.choice(fake.SURNAMES)}",
                                                             "certainty": R.randint(1, 5)}},
        "Origin": lambda: {"native": who, "origin": p.ref("Settlement")},
        "LanguageSpoken": lambda: {"speaker": who, "language": p.ref("Language"), "fluency": R.randint(1, 5)},
        "Ownership": lambda: {"owner": p.agent(), "owned": p.ref(R.choice(["Ship", "Painting", "Manuscript", "Book"]))},
        "LocatedIn": lambda: {"involves": [], "place": p.ref("Building"), "within": p.ref("Settlement")},
        "OccupationAscription": lambda: {"person": who, "has_type": [p.ref("OccupationType")]},
        "Report": lambda: report(p, R.choices([1, 2, 3, 4], [4, 3, 2, 1])[0]),
        "Reputation": lambda: {"reputed": p.agent(), "reputation": R.choice(fake.TRAITS), "favourable": R.random() < 0.5},
    }
    body = makers[kind]()
    return {**base(kind, lbl, f"The source says: {kind.lower()} ({lbl})."), **body}


KINDS: list[str] = []  # filled at import below


def order(p: Pool) -> dict:
    inner_kind = R.choice(["Gift", "Payment", "Letter"])
    inner = make(p, inner_kind)
    # (the bound field: who receives the order gives, pays or sends, so it is left out of what is ordered)
    for f in ("given_by", "payer", "sender"):
        inner.pop(f, None)
    return {"date": fake.any_date(), "places": p.places(), "ordered_by": p.agent_or_identified(),
            "ordered_to": p.agent(),
            "thing_ordered": {"type": R.choice(["PositiveSubjunctive", "NegativeSubjunctive"]), "contents": [inner]}}


def witness(p: Pool) -> dict:
    """Attributed[InRole[Identification[WeightedAlternative[Person]]]]: four reified relations deep"""
    return {"type": "Attributed", "attributed_by": f"the notary {R.choice(fake.SURNAMES)}", "target": [
        {"type": "InRole", "role": R.choice(["witness", "witness", "host", "messenger"]), "target": [p.identified()]}]}


def seal() -> dict:
    """Seal > SealImpression > SealMatrix: embedded three deep"""
    return {"type": "Seal", "condition": R.choice(["intact", "chipped", "fragment", "lost, tag remains"]),
            "impression": {"type": "SealImpression", "wax_colour": R.choice(["red", "green", "brown", "natural"]),
                           "matrix": {"type": "SealMatrix", "engraved_by": R.choice(fake.SURNAMES),
                                      "motto": R.choice(["Fide et labore", "Nisi Dominus", "Semper idem"])}}}


def deep_order(p: Pool, depth: int) -> dict:
    """An order to order (to order ...) a gift, payment or letter; `depth` orders"""
    o = {"type": "Order", **base("Order", f"Order ({R.randint(1, 10**6)})", "An order."), **order(p)}
    for _ in range(depth - 1):
        outer = {"type": "Order", **base("Order", f"Order ({R.randint(1, 10**6)})", "An order to order."), **order(p)}
        outer["thing_ordered"]["contents"] = [o]
        o = outer
    return o


def report(p: Pool, depth: int) -> dict:
    """A report of a report (of a report ...) of a statement; at the bottom, sometimes an order of an order of an order"""
    if depth <= 1:
        inner = deep_order(p, R.randint(2, 4)) if R.random() < 0.4 else make(p, R.choice([k for k in KINDS if k != "Report"]))
    else:
        inner = {**base("Report", f"Report ({R.randint(1, 10**6)})", "Someone reported."), **report(p, depth - 1)}
    return {"reporter": p.agent(), "reported": {"type": "Hearsay", "contents": [inner]}}


def statement(p: Pool) -> dict:
    k = R.random()
    if k < 0.08:
        return {"type": "Negative", "contents": [make(p, R.choice(KINDS))]}
    if k < 0.14:
        return {"type": "Hypothetical", "contents": [make(p, R.choice(KINDS))]}
    if k < 0.19:
        return {"type": "Causes", "cause": make(p, R.choice(KINDS)), "result": make(p, R.choice(KINDS))}
    return make(p, R.choice(KINDS))


def factoid(p: Pool, i: int) -> dict:
    return {
        "label": f"Factoid {i}: what the source says of {R.choice(fake.SURNAMES)}",
        "source": p.source(),
        "statements": [statement(p) for _ in range(R.choices([1, 2, 3, 4], [4, 3, 2, 1])[0])],
        "recorded_on": f"2026-{R.randint(1, 10):02}-{R.randint(1, 28):02}" if R.random() < 0.5 else None,
    }


def _kinds() -> list[str]:
    import inspect

    src = inspect.getsource(make)
    import re

    return re.findall(r'^\s+"([A-Z][A-Za-z]+)": lambda', src, re.M)


KINDS.extend(_kinds())
