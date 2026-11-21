"""The classes of the measurement's heads"""

from pangloss_models import Document, Entity
from pangloss_vectors import VectorsMeta


class Person(Entity):
    _vectors_meta = VectorsMeta(searchable=True)


class Saint(Person):
    pass


class Event(Document):
    pass


class Birth(Event):
    pass


class Creation(Event):
    pass


class CreationOfArtwork(Creation):
    pass


class CreationOfPainting(CreationOfArtwork):
    pass
