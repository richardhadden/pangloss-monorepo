from pytest import raises

from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.model_registry import ModelRegistry


def test_model_manager_cannot_be_initialised_or_subclassed():

    with raises(PanglossInitialisationError):
        ModelRegistry()

    with raises(PanglossInitialisationError):

        class NotAllowedSubclassing(ModelRegistry):
            pass
