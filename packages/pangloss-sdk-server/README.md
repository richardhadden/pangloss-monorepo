# pangloss-sdk-server

Optional. Builds the SDK of a project (its model modules and their type stubs, as a Python package that depends on
`pangloss-sdk`), checks it on a clean client, and serves it under `/api/sdk`: the manifest, a wheel and sdist, a read-only `git`
repository, and a package index (access set by `SDK_ACCESS`). It also tells a client when its SDK is out of date.

Add `"pangloss_sdk_server"` to `INSTALLED_APPS`; the SDK is built as the server starts, or with `pangloss sdk build`
(`status`, `show`).

Guide: [guide/sdk](../../guide/sdk/README.md). Design and history: [docs/sdk.md](../../docs/sdk.md).
