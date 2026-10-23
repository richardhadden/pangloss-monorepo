# pangloss-sdk-server

Optional. Builds the SDK of a project (its model modules and their type stubs, as a Python package
that depends on `pangloss-sdk`) and, in later phases, serves it. Add `"pangloss_sdk_server"` to
`INSTALLED_APPS`, then `pangloss sdk build`.

The design is in [docs/sdk.md](../../docs/sdk.md).
