# pangloss-zotero

Optional. Keeps a Zotero library in the database, **one way**: from Zotero. Add `"pangloss_zotero"` to
`INSTALLED_APPS`. A Zotero item is an entity that can be the source of a factoid and what a factoid is about.

The design is in [docs/zotero.md](../../docs/zotero.md) and [docs/zotero-sources.md](../../docs/zotero-sources.md).

```python
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta


class TextObject(ZoteroBacked):
    """Anything that is a text"""


class Atlas(TextObject):
    _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])
```

Settings (on the project's settings class): `ZOTERO_API_KEY`, `ZOTERO_LIBRARIES` (`["groups/2556736"]`),
`ZOTERO_WATCH` (default `True`), `ZOTERO_SKIP_TYPES`, `ZOTERO_SYNC_USER`.
Commands: `pangloss zotero sync | watch | status | check`.
