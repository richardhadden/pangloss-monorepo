from pytest import fixture

from pangloss_models.model_registry import ModelRegistry


@fixture(scope="function", autouse=True)
def reset_model_registry():

    ModelRegistry._reset()
    yield
