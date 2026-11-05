"""The SDK as a storage backend: the models' functions are requests to a Pangloss server's API"""

from pangloss_core import Storage

api = Storage(name="api", package="pangloss_sdk.databases.api")
api_sync = Storage(name="api (sync)", package="pangloss_sdk.databases.api_sync")
