"""The item types of Zotero, and `ZoteroMeta`: which Zotero types a model class stands for.

    class Atlas(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])

The types are those of Zotero's schema (https://www.zotero.org/support/kb/item_types_and_fields). Zotero may add
more: an item whose type is not in the enum is still imported (its type is kept as the text Zotero gave).
"""

from dataclasses import dataclass
from enum import Enum

from pangloss_models.meta_slots import register_meta_slot


class ZoteroItemType(Enum):
    ARTWORK = "artwork"
    ATTACHMENT = "attachment"
    ANNOTATION = "annotation"
    AUDIO_RECORDING = "audioRecording"
    BILL = "bill"
    BLOG_POST = "blogPost"
    BOOK = "book"
    BOOK_SECTION = "bookSection"
    CASE = "case"
    COMPUTER_PROGRAM = "computerProgram"
    CONFERENCE_PAPER = "conferencePaper"
    DATASET = "dataset"
    DICTIONARY_ENTRY = "dictionaryEntry"
    DOCUMENT = "document"
    EMAIL = "email"
    ENCYCLOPEDIA_ARTICLE = "encyclopediaArticle"
    FILM = "film"
    FORUM_POST = "forumPost"
    HEARING = "hearing"
    INSTANT_MESSAGE = "instantMessage"
    INTERVIEW = "interview"
    JOURNAL_ARTICLE = "journalArticle"
    LETTER = "letter"
    MAGAZINE_ARTICLE = "magazineArticle"
    MANUSCRIPT = "manuscript"
    MAP = "map"
    NEWSPAPER_ARTICLE = "newspaperArticle"
    NOTE = "note"
    PATENT = "patent"
    PODCAST = "podcast"
    PREPRINT = "preprint"
    PRESENTATION = "presentation"
    RADIO_BROADCAST = "radioBroadcast"
    REPORT = "report"
    STANDARD = "standard"
    STATUTE = "statute"
    THESIS = "thesis"
    TV_BROADCAST = "tvBroadcast"
    VIDEO_RECORDING = "videoRecording"
    WEBPAGE = "webpage"


# (items that are not works: they belong to another item)
CHILD_TYPES = ("attachment", "note", "annotation")


@dataclass(frozen=True)
class ZoteroMeta:
    """What a model class stands for in Zotero.

    `item_types`: the Zotero types the class is for. A type that two classes claim needs one of them to say
    `default=True`; nothing is chosen for you. `fallback`: the class for items whose type no class claims (at
    most one; without one, they are imported as `ZoteroObject`)."""

    item_types: tuple[ZoteroItemType | str, ...] = ()
    default: bool = False
    fallback: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_types", tuple(self.item_types))

    @property
    def type_names(self) -> tuple[str, ...]:
        return tuple(
            t.value if isinstance(t, ZoteroItemType) else str(t)
            for t in self.item_types
        )


SLOT = "_zotero_meta"
register_meta_slot(SLOT, ZoteroMeta)
