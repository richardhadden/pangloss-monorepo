"""Invented early modern data for the smoke test: names, places, dates. Deterministic (seeded)"""

import random

import os

# (SMOKE_RUN=2 and up: another run of the ingest, with other names and dates)
R = random.Random(1517 + 1000 * (int(os.environ.get("SMOKE_RUN", "1")) - 1))

FIRST_M = """Giovanni Pietro Antonio Francesco Lorenzo Cosimo Niccolò Bernardo Jacopo Matteo Andrea Tommaso Luca Marco
Johann Hans Jakob Konrad Heinrich Ulrich Georg Albrecht Friedrich Wilhelm Sebastian Kaspar Martin Philipp
Jean Pierre Jacques Guillaume François Louis Nicolas Étienne Michel Claude Antoine Henri Charles
Juan Pedro Diego Alonso Fernando Rodrigo Gonzalo Hernando Francisco Luis Martín
John Thomas William Richard Robert Henry Edward Walter Hugh Nicholas Ralph Roger
Jan Willem Pieter Cornelis Hendrik Dirk Joost Maarten Lucas""".split()
FIRST_F = """Caterina Maria Lucrezia Isabella Margherita Giovanna Bianca Clarice Ginevra Lisabetta
Anna Margarethe Katharina Elisabeth Barbara Ursula Agnes Dorothea Magdalena Apollonia
Jeanne Marguerite Marie Catherine Isabeau Louise Anne Madeleine
Juana Isabel María Leonor Beatriz Catalina Inés Teresa
Alice Joan Agnes Margery Elizabeth Mary Cecily Eleanor
Grietje Aleid Machteld Geertruid Neeltje""".split()
SURNAMES = """Medici Strozzi Pazzi Rucellai Albizzi Tornabuoni Sforza Visconti Gonzaga Este Malatesta Orsini Colonna
Fugger Welser Hochstetter Imhoff Behaim Pirckheimer Tucher Holzschuher Paumgartner Rehlinger
Coeur Briçonnet Beaune Lallemand Jacquelin Gaillard Bohier Duprat Robertet
Mendoza Guzmán Velasco Pimentel Zúñiga Enríquez Toledo Manrique Cerda
Gresham Cavendish Howard Percy Neville Stanley Talbot Cecil Seymour Dudley
Bicker Hooft Pauw Huydecoper Reael Witsen Graeff Bas Oetgens
Contarini Morosini Venier Grimani Loredan Mocenigo Dandolo Foscari Barbarigo
Spinola Doria Grimaldi Centurione Pallavicino Lomellini Giustiniani""".split()
TOWNS = """Florence Venice Genoa Milan Rome Naples Bologna Ferrara Mantua Siena Pisa Lucca Padua Verona
Augsburg Nuremberg Ulm Cologne Frankfurt Strasbourg Basel Vienna Prague Leipzig Lübeck Hamburg
Antwerp Bruges Ghent Amsterdam Leiden Delft Utrecht Haarlem
Lyon Paris Rouen Tours Bordeaux Toulouse Marseille Dijon
Seville Toledo Valladolid Burgos Barcelona Valencia Lisbon Porto
London Bristol York Norwich Oxford Cambridge Southampton""".split()
SUFFIX = ["", "", "", " di Sopra", " di Sotto", " am Main", " an der Donau", "-sur-Mer", " la Vieja", " Magna", " Parva", " Nova"]
REGIONS = """Tuscany Lombardy Veneto Liguria Romagna Piedmont Swabia Franconia Bavaria Saxony Bohemia Austria Brabant Flanders
Holland Zeeland Burgundy Normandy Provence Gascony Castile Aragon Andalusia León Navarre Kent Essex Yorkshire Wessex""".split()
BUILDING_KINDS = ["Church of St", "Palazzo", "Chapel of St", "Hospital of St", "Warehouse of", "House of", "Convent of St", "Bridge of", "Tower of", "Exchange of"]
SAINTS = """Mark John Peter Paul Andrew James Lawrence Stephen George Michael Nicholas Catherine Agnes Clare Francis Dominic
Benedict Ambrose Augustine Jerome Gregory Martin Anne Mary Barbara Ursula Sebastian Roch Anthony""".split()
CRAFTS = ["wool", "silk", "goldsmiths", "bakers", "butchers", "masons", "painters", "printers", "apothecaries", "furriers", "weavers", "dyers", "carpenters", "brewers", "shoemakers"]
COMMODITIES = """pepper cinnamon cloves nutmeg ginger saffron alum wool silk cotton linen fustian velvet damask brocade
copper silver gold tin lead iron mercury salt wine grain wheat barley rye oats herring cod timber pitch tar
hemp flax indigo cochineal woad madder sugar honey wax tallow leather furs amber coral pearls glass paper ink
soap olive-oil almonds raisins figs dates rice cheese butter beer hops tobacco cocoa coffee tea porcelain""".split()
CURRENCIES = """florin ducat gulden thaler écu livre-tournois pound-sterling mark-lübeck real maravedí scudo lira grosso
stuiver denier kreuzer albus batzen crown angel noble sovereign testone zecchino pistole doubloon escudo""".split()
LANGUAGES = [("Latin", "la"), ("Italian", "it"), ("German", "de"), ("French", "fr"), ("Spanish", "es"), ("Portuguese", "pt"),
             ("English", "en"), ("Dutch", "nl"), ("Greek", "el"), ("Hebrew", "he"), ("Arabic", "ar"), ("Czech", "cs"),
             ("Polish", "pl"), ("Hungarian", "hu"), ("Turkish", "tr"), ("Catalan", "ca"), ("Occitan", "oc"), ("Danish", "da"),
             ("Swedish", "sv"), ("Low German", "nds")]
OFFICE_KINDS = ["Bishop of", "Archbishop of", "Doge of", "Podestà of", "Mayor of", "Consul of", "Chancellor of", "Treasurer of",
                "Abbot of", "Prior of", "Duke of", "Count of", "Margrave of", "Gonfaloniere of", "Bailiff of", "Sheriff of",
                "Captain of", "Rector of", "Notary of", "Factor in"]
OCCUPATIONS = {
    "Merchant": ["Banker", "Spice merchant", "Cloth merchant", "Factor", "Money changer"],
    "Cleric": ["Bishop", "Priest", "Monk", "Friar", "Nun", "Canon", "Cardinal"],
    "Craftsman": ["Goldsmith", "Weaver", "Mason", "Printer", "Shoemaker", "Carpenter"],
    "Artist": ["Painter", "Sculptor", "Architect", "Engraver"],
    "Scholar": ["Humanist", "Physician", "Lawyer", "Astronomer", "Teacher"],
    "Official": ["Notary", "Chancellor", "Ambassador", "Secretary", "Treasurer"],
    "Soldier": ["Condottiere", "Captain", "Mercenary", "Knight"],
    "Mariner": ["Captain (ship)", "Pilot", "Sailor"],
}
TITLES = {"Prince": ["King", "Duke", "Margrave", "Count palatine"], "Noble": ["Count", "Baron", "Viscount", "Lord"],
          "Knight": ["Knight bachelor", "Knight banneret"], "Ecclesiastical": ["Cardinal", "Archbishop", "Bishop", "Abbot"]}
TRAITS = ["pious", "avaricious", "learned", "cruel", "generous", "prudent", "quarrelsome", "eloquent", "melancholy", "devout",
          "cunning", "brave", "lazy", "witty", "proud", "humble"]
DESCRIPTIONS = ["tall, with a red beard", "short and stout", "lame in the left leg", "with a scar on the cheek", "fair-haired",
                "dark, with a hooked nose", "very fat in old age", "blind in one eye", "handsome, by all accounts"]
FAITHS = ["Catholic", "Lutheran", "Reformed", "Jewish", "Muslim", "Anabaptist", "Anglican"]
CHARGES = ["usury", "heresy", "theft", "murder", "debt", "slander", "sorcery", "fraud", "smuggling", "treason"]
THEMES = ["penance", "the Last Judgement", "charity", "usury", "the Eucharist", "the Turk", "the Virgin", "vanity"]
DEGREES = ["BA", "MA", "doctor of laws", "doctor of medicine", "doctor of theology", "licentiate in canon law"]


def person_name() -> tuple[str, str, str]:
    gender = R.choice(["male", "male", "female"])
    first = R.choice(FIRST_M if gender == "male" else FIRST_F)
    return first, R.choice(SURNAMES), gender


def year(lo: int = 1450, hi: int = 1640) -> int:
    return R.randint(lo, hi)


def any_date(lo: int = 1450, hi: int = 1640) -> dict:
    """A date of any kind, as a source might give it"""
    y = year(lo, hi)
    k = R.random()
    if k < 0.35:
        return {"type": "ExactDate", "year": y, "month": R.randint(1, 12), "day": R.randint(1, 28)}
    if k < 0.55:
        return {"type": "ExactDate", "year": y, "month": R.randint(1, 12)}
    if k < 0.7:
        return {"type": "ExactDate", "year": y}
    if k < 0.82:
        return {"type": "EDTFDate", "edtf": f"{y}{R.choice(['~', '?', '%'])}"}
    if k < 0.94:
        return {"type": "DateRange", "not_before": {"type": "ExactDate", "year": y},
                "not_after": {"type": "ExactDate", "year": y + R.randint(1, 10)}}
    return {"type": "UnknownDate"}


def single_date(lo: int = 1450, hi: int = 1640) -> dict:
    d = any_date(lo, hi)
    return d


def period(lo: int = 1450, hi: int = 1630) -> dict:
    y = year(lo, hi)
    k = R.random()
    start = {"type": "ExactDate", "year": y}
    if k < 0.7:
        end = {"type": "ExactDate", "year": y + R.randint(0, 25)}
    elif k < 0.85:
        end = {"type": "UnknownDate"}
    else:
        end = {"type": "OngoingDate"}
    if R.random() < 0.1:
        start, end = {"type": "UnknownDate"}, {"type": "ExactDate", "year": y}
    return {"type": "Period", "start": start, "end": end}


def birth_date() -> dict:
    k = R.random()
    y = year(1420, 1610)
    if k < 0.4:
        return {"type": "ExactDate", "year": y}
    if k < 0.6:
        return {"type": "ExactDate", "year": y, "month": R.randint(1, 12), "day": R.randint(1, 28)}
    if k < 0.8:
        return {"type": "EDTFDate", "edtf": f"{y}~"}
    return {"type": "UnknownDate"}
