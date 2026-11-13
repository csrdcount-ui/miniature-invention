from decimal import Decimal

import pytest

from app import engine as eng
from app.engine import ContractTerms, D, calculate


def terms(**kw):
    base = dict(
        annual_volume_mwh=D(100),
        term_months=60,
        markup_pln_mwh=D(100),
        broker_share_pct=D(75),
        first_tranche_pct=D(50),
        trader_share_pct=D(40),
    )
    base.update(kw)
    return ContractTerms(**base)


def test_przyklad_z_praktyki_rynkowej():
    """100 MWh/rok, 5 lat, narzut 100 zł, broker 75%, junior 40%, transza 50%."""
    b = calculate(terms())
    assert b.total_volume_mwh == D(500)
    assert b.total_markup == D("50000.00")
    assert b.broker.total == D("37500.00")
    assert b.trader.total == D("20000.00")
    assert b.owner_margin.total == D("17500.00")
    assert b.broker.tranche1 == D("18750.00")
    assert b.trader.tranche1 == D("10000.00")
    assert b.broker.remaining_invoices == D("18750.00")
    assert b.warnings == []


@pytest.mark.parametrize("share,expected", [("77", "38500.00"), ("75", "37500.00"), ("70", "35000.00")])
def test_rozne_spolki_rozne_udzialy(share, expected):
    b = calculate(terms(broker_share_pct=D(share)))
    assert b.broker.total == D(expected)
    # handlowiec zawsze od całego narzutu, niezależnie od spółki
    assert b.trader.total == D("20000.00")


@pytest.mark.parametrize("tranche", ["30", "50", "0", "100"])
def test_handlowiec_dziedziczy_procent_transzy(tranche):
    b = calculate(terms(first_tranche_pct=D(tranche)))
    ratio = D(tranche) / 100
    assert b.broker.tranche1 == (b.broker.total * ratio).quantize(D("0.01"))
    assert b.trader.tranche1 == (b.trader.total * ratio).quantize(D("0.01"))


def test_override_od_narzutu():
    b = calculate(terms(manager_override_pct=D(5)))
    assert b.manager_override.total == D("2500.00")
    assert b.owner_margin.total == D("15000.00")


def test_override_od_prowizji_handlowca():
    b = calculate(terms(manager_override_pct=D(10), manager_override_base=eng.OVERRIDE_OD_HANDLOWCA))
    assert b.manager_override.total == D("2000.00")
    assert b.owner_margin.total == D("15500.00")


def test_sumy_skladnikow_zgadzaja_sie_co_do_grosza():
    b = calculate(
        terms(
            annual_volume_mwh=D("123.457"),
            term_months=37,
            markup_pln_mwh=D("87.33"),
            broker_share_pct=D("73.3"),
            first_tranche_pct=D("33.3"),
            trader_share_pct=D("41.7"),
            manager_override_pct=D("4.4"),
            new_connection=True,
        )
    )
    for p in (b.broker, b.trader, b.manager_override, b.owner_margin):
        assert p.first_period_invoices + p.tranche1 + p.remaining_invoices == p.total
    assert b.trader.total + b.manager_override.total + b.owner_margin.total == b.broker.total


def test_nowe_przylacze_pierwszy_rok_z_faktur():
    b = calculate(terms(new_connection=True, new_connection_months=12))
    # 12 z 60 miesięcy = 20% z faktur, transza 50% od pozostałych 80%
    assert b.broker.first_period_invoices == D("7500.00")
    assert b.broker.tranche1 == D("15000.00")
    assert b.broker.remaining_invoices == D("15000.00")
    assert b.trader.first_period_invoices == D("4000.00")
    assert b.trader.tranche1 == D("8000.00")


def test_nowe_przylacze_krotsze_niz_okres_historii():
    b = calculate(terms(new_connection=True, term_months=12, new_connection_months=12))
    assert b.broker.first_period_invoices == b.broker.total
    assert b.broker.tranche1 == 0


def test_ostrzezenie_gdy_wlasciciel_dokłada():
    b = calculate(terms(broker_share_pct=D(60), trader_share_pct=D(50), manager_override_pct=D(15)))
    assert b.owner_margin.total < 0
    assert b.warnings


def test_okres_niepelnych_lat():
    b = calculate(terms(term_months=18))
    assert b.total_volume_mwh == D(150)


@pytest.mark.parametrize(
    "kw",
    [
        dict(broker_share_pct=D(101)),
        dict(trader_share_pct=D(-1)),
        dict(annual_volume_mwh=D(0)),
        dict(term_months=0),
        dict(markup_pln_mwh=D(-5)),
        dict(manager_override_base="cos"),
    ],
)
def test_walidacja(kw):
    with pytest.raises(eng.EngineError):
        calculate(terms(**kw))


def test_korekta_proporcjonalna_przy_zerwaniu():
    b = calculate(terms())
    # Wypłacono pierwsze transze (50%), klient zerwał po 12 z 60 miesięcy (20%)
    k = eng.clawback(
        b,
        paid_broker=b.broker.tranche1,
        paid_trader=b.trader.tranche1,
        paid_override=D(0),
        earned_ratio=D("0.2"),
    )
    assert k.broker == D("11250.00")  # 18750 - 7500
    assert k.trader == D("6000.00")  # 10000 - 4000
    assert k.owner_margin == D("5250.00")


def test_korekta_brak_gdy_zarobione_wiecej_niz_wyplacone():
    b = calculate(terms())
    k = eng.clawback(b, paid_broker=D(1000), paid_trader=D(500), paid_override=D(0), earned_ratio=D("0.5"))
    assert k.broker == 0 and k.trader == 0


def test_korekta_wylaczona():
    b = calculate(terms())
    k = eng.clawback(
        b, paid_broker=b.broker.tranche1, paid_trader=b.trader.tranche1, paid_override=D(0),
        earned_ratio=D(0), mode=eng.KOREKTA_BRAK,
    )
    assert k.broker == 0


def test_D_przecinek_i_spacje():
    assert D("1 234,5") == Decimal("1234.5")
    assert D(0.1) + D(0.2) == Decimal("0.3")


def test_kwota_wklejona_z_twarda_spacja():
    from app.engine import D
    assert D("11 550,00") == Decimal("11550.00")
    assert D("11 550,5") == Decimal("11550.5")
    assert D("11 550") == Decimal("11550")
