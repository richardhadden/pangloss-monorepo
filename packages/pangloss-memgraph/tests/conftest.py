from pangloss_models.model_registry import ModelRegistry
from pytest import fixture


@fixture(scope="function", autouse=True)
def reset_model_registry():

    ModelRegistry._reset()
    yield
