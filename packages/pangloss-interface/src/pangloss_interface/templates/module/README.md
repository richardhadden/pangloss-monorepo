# Interface module of `{{app}}`

A Solid 2.0 library that the interface (`pangloss interface build`) includes when `{{app}}` is in `INSTALLED_APPS`.

- `src/index.ts` is the **manifest**: `defineModule({ name, requires, components, routes })`. Everything a model or a route can
  name is a key of `components`.
- A model uses a component in Python: `InterfaceMeta(list_page="{{app}}:Name", item_page=..., view_card=..., edit_card=...)`.
  A subclass inherits what it does not set; `False` turns an inherited one off.
- Links in the navigation bar are not here: they are in `{{app}}/interface_config.py` (`InterfaceConfig`).
- Props of each kind of component: `ListPageProps`, `ItemPageProps`, `ViewCardProps`, `EditCardProps` (from `@pangloss/interface-core`).
- Use the interface's own components with `useComponent("Button")`, `"Console"`, `"ResultButton"`, ...; they are the ones a project
  may have replaced. Use Tailwind for all CSS. A module is rendered on the server too: no `window` outside an effect.

Check it: `pangloss interface check`. Develop it: `pangloss interface dev` (or `--link`).
