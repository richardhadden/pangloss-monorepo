import pytest
from pangloss_core import settings
from pydantic import ValidationError


class Settings(settings.ClientSettings):
    pass


def test_a_settings_object_that_fails_validation_leaves_the_previous_one():
    good = Settings(INSTALLED_APPS=[], STORAGE="somewhere:storage")
    assert settings.SETTINGS is good

    with pytest.raises(ValidationError):
        Settings(INSTALLED_APPS="not a list")

    assert settings.SETTINGS is good
    assert settings.SETTINGS.STORAGE == "somewhere:storage"


def test_the_storage_backend_is_named_by_storage():
    from pangloss_core import storage

    made = Settings(INSTALLED_APPS=[], STORAGE="pangloss_memgraph:storage")
    assert settings.get_settings() is made
    backend = storage.storage_of(made)
    assert backend.name == "memgraph"
    assert backend.package == "pangloss_memgraph.databases.memgraph"
    assert backend.capabilities.cypher


def test_database_module_is_still_read_with_a_warning():
    from pangloss_core import storage

    with pytest.warns(DeprecationWarning, match="STORAGE"):
        made = Settings(
            INSTALLED_APPS=[], DATABASE_MODULE="pangloss_neo4j.databases.neo4j"
        )
    assert storage.storage_of(made).name == "neo4j"
    # (a module that is not a known backend's is a backend with nothing more than its parts)
    with pytest.warns(DeprecationWarning):
        other = Settings(INSTALLED_APPS=[], DATABASE_MODULE="somewhere.else")
    assert storage.storage_of(other).package == "somewhere.else"
    assert not storage.storage_of(other).capabilities.cypher


def test_settings_without_a_storage_backend_are_refused():
    with pytest.raises(ValidationError, match="STORAGE is required"):
        Settings(INSTALLED_APPS=[])


def test_a_storage_reference_that_is_not_one_says_so():
    from pangloss_core import storage

    for reference, message in [
        ("pangloss_memgraph", "module:attribute"),
        ("pangloss_memgraph:nothing", "Cannot find"),
        ("pangloss_core.storage:Capabilities", "is not a storage backend"),
    ]:
        with pytest.raises(storage.PanglossStorageError, match=message):
            storage.load(reference)
