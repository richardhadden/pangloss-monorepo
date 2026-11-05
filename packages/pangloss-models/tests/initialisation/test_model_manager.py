from pangloss_models import ModelRegistry, PanglossInitialisationError
from pytest import raises


def test_model_manager_cannot_be_initialised_or_subclassed():

    with raises(PanglossInitialisationError):
        ModelRegistry()

    with raises(PanglossInitialisationError):

        class NotAllowedSubclassing(ModelRegistry):
            pass
