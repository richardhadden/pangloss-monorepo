# Migrations: a user guide

*Part of the [Pangloss guides](../README.md). New to Pangloss? Start with [Getting started](../getting-started/README.md).*

Your models describe what your data looks like. Your data lives in a database, and it was written when the models looked different. A **migration** is a small file that says how to bring the data from the old shape to the new one, so that the two never disagree.

You change a model, run two commands, and the data follows:

```bash
pangloss makemigrations     # looks at what you changed, writes a migration file
pangloss migrate            # applies it to the database
```

Pangloss works out most of what to do. It asks you about the few things only you can know (was this field renamed, or removed and a new one added? what value should existing records get?), keeps your answers in the migration file, and checks afterwards that all your data can still be read with the new models.

## How to read this guide

| Chapter | Read it when |
|---------|--------------|
| [1. The ideas](01-ideas.md) | You want the mental model first (10 minutes) |
| [2. Everyday workflow](02-workflow.md) | You are changing a model and need the commands |
| [3. What happens for each kind of change](03-changes.md) | You want to know what a change to a model does to the data, and what you will be asked |
| [4. Staying safe](04-safety.md) | You are migrating data you care about: dry runs, backups, large databases |
| [5. Going back, and squashing](05-back-and-squash.md) | You want to undo a migration, or tidy a long history |
| [6. Writing a migration by hand](06-by-hand.md) | Pangloss refused a change, or you need to move data in a way it cannot guess |
| [7. Several apps, existing databases, teams](07-projects.md) | Your project has more than one app, a database from before migrations, or more than one developer |
| [8. When something goes wrong](08-troubleshooting.md) | An error, a stuck lock, a failed migration |
| [9. Memgraph: what is specific to it](09-memgraph.md) | Backups (snapshots and how long they last), indexes and constraints, writing Cypher against Pangloss data |

If you only read one chapter, read [2](02-workflow.md); if you only read two, add [4](04-safety.md). Everything that depends on the database being Memgraph is in [9](09-memgraph.md).

## Cheat sheet

```bash
pangloss makemigrations                  # write migrations for what changed in the models
pangloss makemigrations --dry-run        # show them without writing
pangloss makemigrations --check          # exit 1 if the models have changed (for CI)
pangloss makemigrations myapp            # only that app's migrations (and what they need)
pangloss makemigrations --empty myapp    # an empty migration, to write by hand

pangloss showmigrations                  # what is applied ([X]) and what is not ([ ])
pangloss migrate --plan                  # what would be applied
pangloss migrate --dry-run               # try it in a transaction that is rolled back
pangloss migrate --backup                # take a backup (a Memgraph snapshot), then apply
pangloss migrate                         # apply what is pending

pangloss migrate myapp 0002              # go to a migration (backwards if it is already applied)
pangloss migrate myapp zero              # undo all of an app's migrations
pangloss squashmigrations myapp 0001 0007
pangloss cleanmigrations myapp           # delete the originals of a squashed migration

pangloss backups                         # the backups the server has
pangloss restore PATH                    # put the database back to one (replaces everything)

pangloss check-data                      # read all the data with the current models
```
