from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TypedDict

type BaseTypes = str | int | float | bool | Decimal | Enum | date | datetime | TypedDict
