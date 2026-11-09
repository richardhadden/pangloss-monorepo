# Interface module of `pangloss_users`

A Solid 2.0 library that the interface includes when `pangloss_users` is in `INSTALLED_APPS`. For someone logged in:

- `/users` (`UsersPage`, linked from the navigation bar): everyone, by username and full name.
- `/users/:username` (`UserPage`): the entities and top-level documents the user has made or changed, the most recent
  first, a page at a time.
- `userHref` in the manifest: the console's "created" and "modified" names link to that page.
