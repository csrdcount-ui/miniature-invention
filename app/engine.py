"""Silnik prowizji platformy brokerskiej.

Czyste funkcje bez bazy danych i bez sieci — łatwe do przetestowania.
Wszystkie kwoty liczone na Decimal, zaokrąglane do grosza na końcu.

Baza procentów (ważne, łatwo się pomylić):
- udział brokera u spółki obrotu: % CAŁEJ masy narzutu,
- udział handlowca: % CAŁEJ masy narzutu (nie udziału brokera),
- override menedżera: % całej masy narzutu ALBO % kwoty handlowca
  (wybiera właściciel w ustawieniach menedżera),
- procent pierwszej transzy: % kwoty DANEJ STRONY (broker, handlowiec,
  menedżer dostają ten sam procent swojej części — handlowiec dziedziczy
  harmonogram spółki proporcjonalnie).

Wszystkie procenty pochodzą z ustawień właściciela (per spółka, per osoba).
Nic tu nie jest zaszyte na stałe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

GROSZ = Decimal("0.01")
STO = Decimal("100")
ZERO = Decimal("0")

OVERRIDE_OD_NARZUTU = "narzut"
OVERRIDE_OD_HANDLOWCA = "udzial_handlowca"
OVERRIDE_BASES = (OVERRIDE_OD_NARZUTU, OVERRIDE_OD_HANDLOWCA)

KOREKTA_PROPORCJONALNA = "proporcjonalna"
KOREKTA_BRAK = "brak"
CLAWBACK_MODES = (KOREKTA_PROPORCJONALNA, KOREKTA_BRAK)


class EngineError(ValueError):
    """Niepoprawne dane wejściowe do silnika prowizji."""


def D(value) -> Decimal:
    """Bezpieczna konwersja na Decimal (float przez str, by uniknąć 0.1+0.2)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if value is None or value == "":
        return ZERO
    # Spacje, także twarde (wklejone z Excela lub wyciągu bankowego), to separatory tysięcy.
    text = str(value)
    for sep in (" ", "\u00a0", "\u202f"):
        text = text.replace(sep, "")
    return Decimal(text.replace(",", "."))


def zl(value: Decimal) -> Decimal:
    return value.quantize(GROSZ, rounding=ROUND_HALF_UP)


def _pct(value: Decimal, name: str) -> Decimal:
    if value < 0 or value > 100:
        raise EngineError(f"{name}: procent musi być w zakresie 0–100, podano {value}")
    return value


@dataclass(frozen=True)
class ContractTerms:
    """Warunki umowy wraz z regułami zamrożonymi w dniu podpisania."""

    annual_volume_mwh: Decimal
    term_months: int
    markup_pln_mwh: Decimal
    broker_share_pct: Decimal
    first_tranche_pct: Decimal
    trader_share_pct: Decimal
    manager_override_pct: Decimal = ZERO
    manager_override_base: str = OVERRIDE_OD_NARZUTU
    new_connection: bool = False
    new_connection_months: int = 12

    def validate(self) -> None:
        if self.annual_volume_mwh <= 0:
            raise EngineError("Wolumen roczny musi być większy od zera")
        if self.term_months <= 0:
            raise EngineError("Okres umowy musi być większy od zera")
        if self.markup_pln_mwh < 0:
            raise EngineError("Narzut nie może być ujemny")
        _pct(self.broker_share_pct, "Udział brokera")
        _pct(self.first_tranche_pct, "Pierwsza transza")
        _pct(self.trader_share_pct, "Udział handlowca")
        _pct(self.manager_override_pct, "Override menedżera")
        if self.manager_override_base not in OVERRIDE_BASES:
            raise EngineError("Nieznana baza override menedżera")
        if self.new_connection and self.new_connection_months < 0:
            raise EngineError("Okres rozliczeń z faktur nie może być ujemny")


@dataclass(frozen=True)
class Payout:
    """Rozkład kwoty jednej strony w czasie.

    first_period_invoices — dla nowych przyłączy: część rozliczana z każdej
        zapłaconej faktury w okresie budowania historii (np. 12 mies.).
    tranche1 — pierwsza transza (z góry / po zbudowaniu historii).
    remaining_invoices — reszta, wypłacana po zapłaconych fakturach.
    """

    total: Decimal
    first_period_invoices: Decimal
    tranche1: Decimal
    remaining_invoices: Decimal


@dataclass(frozen=True)
class Breakdown:
    total_volume_mwh: Decimal
    total_markup: Decimal
    broker: Payout
    trader: Payout
    manager_override: Payout
    owner_margin: Payout
    warnings: list[str] = field(default_factory=list)


def _split(total: Decimal, terms: ContractTerms, invoice_ratio: Decimal) -> Payout:
    total = zl(total)
    first_period = zl(total * invoice_ratio)
    rest = total - first_period
    tranche1 = zl(rest * terms.first_tranche_pct / STO)
    remaining = total - first_period - tranche1
    return Payout(total, first_period, tranche1, remaining)


def calculate(terms: ContractTerms) -> Breakdown:
    """Wylicza pełną masę prowizji i jej podział dla jednej umowy."""
    terms.validate()

    total_volume = terms.annual_volume_mwh * Decimal(terms.term_months) / Decimal(12)
    total_markup = total_volume * terms.markup_pln_mwh

    broker_amt = zl(total_markup * terms.broker_share_pct / STO)
    trader_amt = zl(total_markup * terms.trader_share_pct / STO)
    if terms.manager_override_base == OVERRIDE_OD_HANDLOWCA:
        override_amt = zl(trader_amt * terms.manager_override_pct / STO)
    else:
        override_amt = zl(total_markup * terms.manager_override_pct / STO)

    # Nowe przyłącze: przez pierwsze N miesięcy brak historii, rozliczenie
    # z faktur od rzeczywistego zużycia. Prognozę liczymy od wolumenu
    # deklarowanego — proporcja czasu.
    if terms.new_connection:
        months = min(terms.new_connection_months, terms.term_months)
        invoice_ratio = Decimal(months) / Decimal(terms.term_months)
    else:
        invoice_ratio = ZERO

    broker = _split(broker_amt, terms, invoice_ratio)
    trader = _split(trader_amt, terms, invoice_ratio)
    override = _split(override_amt, terms, invoice_ratio)
    # Marża właściciela = to, co zostaje z udziału brokera — liczona per
    # składnik, żeby sumy się zgadzały co do grosza.
    owner = Payout(
        total=broker.total - trader.total - override.total,
        first_period_invoices=broker.first_period_invoices
        - trader.first_period_invoices
        - override.first_period_invoices,
        tranche1=broker.tranche1 - trader.tranche1 - override.tranche1,
        remaining_invoices=broker.remaining_invoices
        - trader.remaining_invoices
        - override.remaining_invoices,
    )

    warnings: list[str] = []
    if owner.total < 0:
        warnings.append(
            "Prowizja handlowca i override menedżera przekraczają udział brokera — "
            "właściciel dopłaca do tej umowy."
        )
    if terms.markup_pln_mwh == 0:
        warnings.append("Narzut wynosi 0 zł/MWh — umowa nie generuje prowizji.")

    return Breakdown(
        total_volume_mwh=total_volume.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        total_markup=zl(total_markup),
        broker=broker,
        trader=trader,
        manager_override=override,
        owner_margin=owner,
        warnings=warnings,
    )


@dataclass(frozen=True)
class Clawback:
    earned_ratio: Decimal
    broker: Decimal
    trader: Decimal
    manager_override: Decimal
    owner_margin: Decimal


def clawback(
    breakdown: Breakdown,
    *,
    paid_broker: Decimal,
    paid_trader: Decimal,
    paid_override: Decimal,
    earned_ratio: Decimal,
    mode: str = KOREKTA_PROPORCJONALNA,
) -> Clawback:
    """Korekta przy zerwaniu umowy lub niższym zużyciu.

    earned_ratio — jaka część kontraktu została faktycznie zrealizowana
    (np. przepracowane miesiące / okres umowy albo zużyty wolumen /
    wolumen z umowy), od 0 do 1.

    Strona oddaje to, co dostała ponad zarobioną część swojej kwoty.
    Korekta spółki przechodzi proporcjonalnie na handlowca i menedżera,
    a różnica obciąża marżę właściciela.
    """
    if mode not in CLAWBACK_MODES:
        raise EngineError("Nieznany tryb korekty")
    ratio = D(earned_ratio)
    if ratio < 0 or ratio > 1:
        raise EngineError("Zrealizowana część umowy musi być między 0 a 1")
    if mode == KOREKTA_BRAK:
        return Clawback(ratio, ZERO, ZERO, ZERO, ZERO)

    def back(total: Decimal, paid: Decimal) -> Decimal:
        return max(ZERO, zl(D(paid) - total * ratio))

    b = back(breakdown.broker.total, paid_broker)
    t = back(breakdown.trader.total, paid_trader)
    m = back(breakdown.manager_override.total, paid_override)
    return Clawback(ratio, b, t, m, b - t - m)
