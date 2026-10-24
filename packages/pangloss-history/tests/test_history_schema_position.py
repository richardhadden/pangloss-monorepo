from types import SimpleNamespace

from pangloss_history import schema_position as module
from pangloss_models.meta_kit.migrations import files


def migration(app, name):
    return files.Migration(app=app, name=name, changes=())


def test_the_position_is_the_last_migration_of_each_app(monkeypatch):
    graph = files.MigrationGraph.of(
        [
            migration("letters", "0001_initial"),
            migration("letters", "0002_addfield_year"),
            migration("places", "0001_initial"),
        ]
    )
    monkeypatch.setattr(module, "graph_of", lambda apps: graph)
    module.forget()
    assert module.schema_position(["letters", "places"]) == {
        "letters": "0002_addfield_year",
        "places": "0001_initial",
    }


def test_it_is_read_once_until_it_is_forgotten(monkeypatch):
    calls = []

    def graph_of(apps):
        calls.append(apps)
        return SimpleNamespace(migrations={})

    monkeypatch.setattr(module, "graph_of", graph_of)
    module.forget()
    assert module.schema_position(["a"]) == module.schema_position(["a"]) == {}
    assert len(calls) == 1
    module.forget()
    module.schema_position(["a"])
    assert len(calls) == 2
    module.forget()
