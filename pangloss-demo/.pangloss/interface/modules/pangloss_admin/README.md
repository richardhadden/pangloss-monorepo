# The interface module of pangloss_admin

The page `/admin`, for admins only. Another module adds a part to it with `slots: { admin: { Name: loader } }`. A job
needs no interface code: its options are drawn from what the API says of it. See `docs/admin.md`.
