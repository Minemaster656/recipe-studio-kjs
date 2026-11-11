"""A single slot value.

The same class is used for items, tags and fluids.  Recipe modules decide
which kinds they accept.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


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
