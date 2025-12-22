import unittest
from typing import Protocol
from unittest.mock import MagicMock

from litebind import Container


class Contains:  # noqa: PLW1641
    def __init__(self, substring):
        self.substring = substring

    def __repr__(self):
        return f"Contains({self.substring!r})"

    def __eq__(self, other):
        return isinstance(other, str) and self.substring in other


class PaymentClient(Protocol):
    def charge(self, order_id: str, amount_cents: int) -> None: ...


class InfoLogger(Protocol):
    def info(self, msg: object, *args: object) -> None: ...


class NullLogger:
    def info(self, msg: object, *args: object) -> None:
        pass


class StripeSdk:
    def pay(self, amount_usd: float, reference: str) -> bool:
        print(f"Stripe charged ${amount_usd} for {reference}")  # noqa: T201
        return True


class StripeAdapter:
    def __init__(
        self, sdk: StripeSdk, logger: InfoLogger, usd_per_cent: float = 0.01
    ) -> None:
        self._logger = logger
        self._sdk = sdk
        self._usd_per_cent = usd_per_cent

    def charge(self, order_id: str, amount_cents: int) -> None:
        self._logger.info("adapting to stripe sdk api")
        amount_usd = amount_cents * self._usd_per_cent
        ok = self._sdk.pay(amount_usd, reference=order_id)
        if not ok:
            msg = "Stripe payment failed"
            raise RuntimeError(msg)


class TestWiringAdapterThirdPartySDK(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()
        self.cont.register(PaymentClient, StripeAdapter)
        self.stripe_sdk = StripeSdk()
        self.stripe_sdk.pay = MagicMock(wraps=self.stripe_sdk.pay)
        self.cont.register_instance(StripeSdk, self.stripe_sdk)
        self.logger = NullLogger()
        self.logger.info = MagicMock(wraps=self.logger.info)
        self.cont.register_instance(InfoLogger, self.logger)

    def test_adapter_calls_adaptee(self):
        client: PaymentClient = self.cont.resolve(PaymentClient, usd_per_cent=0.0125)
        client.charge("order-123", 5000)

        assert self.stripe_sdk.pay.call_count == 1
        assert self.stripe_sdk.pay.call_args[0][0] == 0.0125 * 5000
        assert self.stripe_sdk.pay.call_args[1]["reference"] == "order-123"

        assert self.logger.info.call_args[0][0] == Contains("stripe sdk")



class TestAutoWiringAdapterThirdPartySDK(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()
        self.cont.register(PaymentClient, StripeAdapter)
        self.cont.register(InfoLogger, NullLogger)

    def test_adapter_calls_adaptee(self):
        client: PaymentClient = self.cont.resolve(PaymentClient, usd_per_cent=0.0125)
        client.charge("order-123", 5000)
