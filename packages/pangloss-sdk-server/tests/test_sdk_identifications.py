"""A project whose fields take the library's identifications (`Identification[...]`, and so the classes below it:
`IdentificationFromText`, `IdentificationByToolchain`, `IdentificationByToolchainFromText`): its SDK builds, passes
the check on a client (the client's models are the server's), and offers the two that keep the text"""

import importlib

import pytest
from pangloss_sdk_server import check, publish
from server_support import load_models, settings_for, write

MODELS = """
    from pangloss_library import Identification, WeightedAlternative
    from pangloss_models import Document, Entity


    class Person(Entity):
        pass


    class Statement(Document):
        by: Person | Identification[WeightedAlternative[Person]]
        witness: Person | Identification[Person]
"""


@pytest.fixture
def identifying(project):
    write(project, {"shop/models.py": MODELS})
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models

    importlib.reload(pangloss_library.models)
    return project


def test_the_sdk_of_fields_that_take_identifications_passes_the_check(identifying):
    load_models()

    built = publish.build(identifying, settings_for())

    assert built.changed
    schemas = check.run_in_clean_process(built.directory, "shop_sdk")
    by = str(schemas["Statement"]["Create"])
    for name in (
        "IdentificationFromText",
        "IdentificationByToolchain",
        "IdentificationByToolchainFromText",
    ):
        assert name in by, name
