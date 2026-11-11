"""A single slot value.

The same class is used for items, tags and fluids.  Recipe modules decide
which kinds they accept.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


FLUID_BUCKET_SUFFIX = "_bucket"


def is_bucket_id(item_id: str) -> bool:
    return str(item_id).endswith(FLUID_BUCKET_SUFFIX)


def fluid_id_from_bucket(item_id: str) -> str:
    """``minecraft:water_bucket`` -> ``minecraft:water``."""
    value = str(item_id).strip()
    if value.endswith(FLUID_BUCKET_SUFFIX):
        return value[: -len(FLUID_BUCKET_SUFFIX)]
    return value


def normalize_fluid_id(fluid_id: str) -> str:
    """Accept either a fluid id or a bucket id and return the fluid id."""
    return fluid_id_from_bucket(fluid_id)


@dataclass
class Ingredient:
    kind: str = "empty"  # empty | item | tag | fluid
    id: str = ""
    count: int = 1
    chance: float | None = None
    nbt: str | None = None
    amount: int | None = None  # fluid amount in mB

    @property
    def is_empty(self) -> bool:
        return self.kind == "empty" or not self.id

    def copy(self) -> "Ingredient":
        return replace(self)

    def clear(self) -> None:
        self.kind = "empty"
        self.id = ""
        self.count = 1
        self.chance = None
        self.nbt = None
        self.amount = None

    def label(self) -> str:
        if self.is_empty:
            return ""
        if self.kind == "tag":
            return "#" + self.id
        if self.kind == "fluid":
            return f"{self.id} ({self.amount or 1000} mB)"
        return self.id + (f" x{self.count}" if self.count > 1 else "")

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "count": self.count,
            "chance": self.chance,
            "nbt": self.nbt,
            "amount": self.amount,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ingredient":
        return cls(
            kind=data.get("kind", "empty"),
            id=data.get("id", ""),
            count=int(data.get("count", 1) or 1),
            chance=data.get("chance"),
            nbt=data.get("nbt"),
            amount=data.get("amount"),
        )
