"""The Neo4j database: `pangloss_cypher.transactions`, with Neo4j's dialect. (Everything else of the transactions is
there, and named here as well, for what imports it from here.)"""

from pangloss_core.settings import BaseSettings
from pangloss_cypher import transactions
from pangloss_cypher.transactions import (
    MAX_LOGGED_QUERY as MAX_LOGGED_QUERY,
)
from pangloss_cypher.transactions import (
    LoggedTransaction as LoggedTransaction,
)
from pangloss_cypher.transactions import (
    Transaction as Transaction,
)
from pangloss_cypher.transactions import (
    current as current,
)
from pangloss_cypher.transactions import (
    install as install,
)
from pangloss_cypher.transactions import (
    installed as installed,
)
from pangloss_cypher.transactions import (
    read_transaction as read_transaction,
)
from pangloss_cypher.transactions import (
    refuse_while_migrating as refuse_while_migrating,
)
from pangloss_cypher.transactions import (
    slow_query_ms as slow_query_ms,
)
from pangloss_cypher.transactions import (
    timed as timed,
)
from pangloss_cypher.transactions import (
    timeout_from_setting as timeout_from_setting,
)
from pangloss_cypher.transactions import (
    using as using,
)
from pangloss_cypher.transactions import (
    write_transaction as write_transaction,
)

from pangloss_neo4j.databases.neo4j.dialect import Neo4jDialect
from pangloss_neo4j.databases.neo4j.settings import Neo4jDatabaseSettings


class Database(transactions.Database):
    settings: BaseSettings[Neo4jDatabaseSettings]
    dialect = Neo4jDialect()
