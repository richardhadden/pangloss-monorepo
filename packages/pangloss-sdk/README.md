# pangloss-sdk

The client side of the SDK: lets a project's models be used from a script or notebook, with every model function a request to
the project's REST API. It needs no database driver and no web framework. `pangloss_sdk.connect`, `check`, `iterate`, a login
that can be kept (`pangloss-sdk login`), `pangloss-sdk update` and `pangloss-sdk sync-stubs`, and the errors a client can raise.

The project's own SDK (its models, with type stubs, as a package) is built and served by
[`pangloss-sdk-server`](../pangloss-sdk-server) and depends on this one.

Guide: [guide/sdk](../../guide/sdk/README.md). Reference: [docs/sdk.md](../../docs/sdk.md). Example: [`sdk-demo/`](../../sdk-demo).
