# Interface module of `pangloss_interface`

The pages for merging two entities that are one (implementation_docs/entity-identity.md, part C). The merge itself is
the core's (`pangloss-cypher`, `pangloss-api`); these pages use the hooks every interface module has. For someone
logged in:

- **Merge with…** in the console of an entity's page (`MergeAction`): a dialog that finds the other entity, and lists
  the merges the entity is part of.
- `/:type/:id/merge/:other` (`ComparePage`): the two side by side, a row for each field, with what the survivor is to
  have. Merges, or proposes the merge for someone else to verify (`MERGE_DIRECTLY`).
- `/merges/:merge` (`MergePage`): one merge. A proposal is the comparison again, to verify or reject; a merge that
  was made says what undoing it would do, and undoes it.
- `/merges` (`MergesPage`): the merges, those that wait for someone first.
- Notices above an entity's contents (`itemNotices`): a merge proposed, an undo proposed, and "was merged into this"
  for someone who came by the address of the entity absorbed.
- On `/admin` (`slots.admin`): the merges made lately.

`src/compare.ts` is the logic of the comparison, without a DOM.
