import sys

# Clear any mocked payments modules set by other test files before importing the real one
for _key in list(sys.modules.keys()):
    if _key.startswith("payments"):
        del sys.modules[_key]

import pytest
from payments.wallet import MockWallet, InsufficientFundsError


def test_create_wallet_returns_id():
    w = MockWallet()
    wid = w.create_wallet("user1")
    assert wid.startswith("mock_")


def test_initial_balance_is_zero():
    w = MockWallet()
    wid = w.create_wallet("user1")
    assert w.get_balance(wid) == 0


def test_credit_increases_balance():
    w = MockWallet()
    wid = w.create_wallet("user1")
    w.credit(wid, 100)
    assert w.get_balance(wid) == 100


def test_pay_deducts_from_sender():
    w = MockWallet()
    wid = w.create_wallet("user1")
    w.credit(wid, 100)
    w.pay(wid, "model_wallet", 40)
    assert w.get_balance(wid) == 60


def test_pay_credits_recipient():
    w = MockWallet()
    sender = w.create_wallet("user1")
    receiver = w.create_wallet("model1")
    w.credit(sender, 100)
    w.pay(sender, receiver, 40)
    assert w.get_balance(receiver) == 40


def test_insufficient_funds_raises():
    w = MockWallet()
    wid = w.create_wallet("user1")
    w.credit(wid, 10)
    with pytest.raises(InsufficientFundsError):
        w.pay(wid, "model_wallet", 50)


def test_pay_returns_transaction_dict():
    w = MockWallet()
    wid = w.create_wallet("user1")
    w.credit(wid, 100)
    tx = w.pay(wid, "model_wallet", 20)
    assert tx["amount_sats"] == 20
    assert tx["direction"] == "debit"
    assert "id" in tx
    assert "timestamp" in tx
