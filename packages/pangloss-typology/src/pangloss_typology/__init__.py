"""Typologies: vocabularies of types in a hierarchy, for entities to have (`has_type`)"""

from pangloss_typology.typology import Typed, Typology, TypologyMeta

__all__ = ["Typed", "Typology", "TypologyMeta", "requires"]

# (what the storage backend must be able to do: the typology runs its own Cypher. Checked at start-up, see
# `pangloss_core.storage.check_requirements`)
requires = {"cypher"}
