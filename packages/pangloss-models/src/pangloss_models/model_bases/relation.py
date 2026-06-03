from pangloss_models.model_bases.base_models import _DeclaredClass
from pangloss_models.model_bases.entity import Entity


class Relation[Subject: type[Entity], Object: type[Entity]](_DeclaredClass):
    subject: Subject
    object: Object
