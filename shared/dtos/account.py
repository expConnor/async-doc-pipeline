from dataclasses import dataclass


@dataclass(frozen=True)
class AccountDTO:
    id: int
    api_key_hash: str | None
