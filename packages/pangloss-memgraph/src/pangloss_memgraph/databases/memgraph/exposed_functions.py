from pangloss_models.model_bases.base_models import _CreateDBBase, _UpdateDBBase


def save(self: _CreateDBBase | _UpdateDBBase):
    print("wahoo!", self)
