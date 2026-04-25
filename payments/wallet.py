import os
import uuid
from datetime import datetime, timezone


class InsufficientFundsError(Exception):
    pass


class MockWallet:
    """
    In-memory Lightning wallet. Matches the interface the real MDK will expose.
    Enabled when USE_MOCK_WALLET=true (default for dev).
    """

    def __init__(self):
        self._balances: dict[str, int] = {}

    def create_wallet(self, owner_id: str) -> str:
        wallet_id = f"mock_{owner_id[:8]}_{uuid.uuid4().hex[:8]}"
        self._balances[wallet_id] = 0
        return wallet_id

    def get_balance(self, wallet_id: str) -> int:
        return self._balances.get(wallet_id, 0)

    def credit(self, wallet_id: str, amount_sats: int) -> dict:
        self._balances.setdefault(wallet_id, 0)
        self._balances[wallet_id] += amount_sats
        return self._tx(wallet_id, amount_sats, "credit")

    def pay(self, from_wallet_id: str, to_wallet_id: str, amount_sats: int) -> dict:
        if self._balances.get(from_wallet_id, 0) < amount_sats:
            raise InsufficientFundsError(
                f"{from_wallet_id} has {self._balances.get(from_wallet_id, 0)} sats, need {amount_sats}"
            )
        self._balances[from_wallet_id] -= amount_sats
        self._balances.setdefault(to_wallet_id, 0)
        self._balances[to_wallet_id] += amount_sats
        return self._tx(from_wallet_id, amount_sats, "debit")

    def _tx(self, wallet_id: str, amount_sats: int, direction: str) -> dict:
        return {
            "id": uuid.uuid4().hex,
            "wallet_id": wallet_id,
            "amount_sats": amount_sats,
            "direction": direction,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def get_wallet() -> MockWallet:
    # Swap this for real MDK client when USE_MOCK_WALLET=false
    return _wallet


_wallet = MockWallet()
