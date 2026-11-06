"""Dane demonstracyjne: python -m app.demo

Tworzy właściciela, menedżera, dwóch handlowców, dwie spółki z różnymi
regułami i kilka umów. Działa tylko na pustej bazie.
Hasło wszystkich kont demo: demo-haslo-123
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from . import services as svc
from .db import Base, SessionLocal, engine
from .migrate import run as migrate
from .models import ROLE_MANAGER, ROLE_OWNER, ROLE_TRADER, Company, Supplier, SupplierRuleSet, User, UserRate
from .security import hash_password

PW = "demo-haslo-123"
START = date(2000, 1, 1)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    migrate(engine)
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            print("Baza nie jest pusta — pomijam dane demo.")
            return
        h = hash_password(PW)
        owner = User(email="wlasciciel@demo.pl", name="Właściciel Demo", first_name="Właściciel", last_name="Demo", password_hash=h, role=ROLE_OWNER)
        mgr = User(email="menedzer@demo.pl", name="Marta Menedżer", first_name="Marta", last_name="Menedżer", password_hash=h, role=ROLE_MANAGER)
        db.add_all([owner, mgr, Company(name="Biuro Brokerskie Demo sp. z o.o.")])
        db.flush()
        t1 = User(email="handlowiec@demo.pl", name="Tomasz Handlowiec", first_name="Tomasz", last_name="Handlowiec", password_hash=h, role=ROLE_TRADER, manager_id=mgr.id)
        t2 = User(email="junior@demo.pl", name="Julia Junior", first_name="Julia", last_name="Junior", password_hash=h, role=ROLE_TRADER, manager_id=mgr.id)
        db.add_all([t1, t2])
        db.flush()
        db.add_all([
            UserRate(user_id=mgr.id, valid_from=START, trader_share_pct=Decimal(45), override_pct=Decimal(5)),
            UserRate(user_id=t1.id, valid_from=START, trader_share_pct=Decimal(45)),
            UserRate(user_id=t2.id, valid_from=START, trader_share_pct=Decimal(35)),
        ])
        a = Supplier(name="Spółka Obrotu Alfa")
        b = Supplier(name="Spółka Obrotu Beta")
        db.add_all([a, b])
        db.flush()
        db.add_all([
            SupplierRuleSet(supplier_id=a.id, valid_from=START, broker_share_pct=Decimal(77), first_tranche_pct=Decimal(30),
                            max_markup_pln_mwh=Decimal(200), new_connection_months=12),
            SupplierRuleSet(supplier_id=b.id, valid_from=START, broker_share_pct=Decimal(70), first_tranche_pct=Decimal(50),
                            first_tranche_trigger="start_dostaw", max_markup_pln_mwh=Decimal(180), new_connection_months=12),
        ])
        db.commit()

        for trader, sup, client, vol, months, markup, new in [
            (t1, a, "Piekarnia Złoty Kłos", 100, 60, 100, False),
            (t1, b, "Chłodnia Lubelska", 850, 36, 85, False),
            (t2, a, "Hotel Pod Lipami", 240, 24, 120, False),
            (t2, b, "Nowa Hala Logistyczna", 600, 48, 90, True),
            (mgr, a, "Zakład Mechaniczny Kowalski", 1200, 36, 70, False),
        ]:
            svc.create_contract(
                db, actor=owner, trader=trader, supplier=sup, client_name=client, client_nip="", medium="energia",
                signed_date=date.today(), start_date=None, term_months=months,
                annual_volume_mwh=Decimal(vol), markup_pln_mwh=Decimal(markup), base_price_pln_mwh=Decimal(480),
                new_connection=new, status="Umowa podpisana",
            )
    print("Dane demo utworzone. Konta: wlasciciel@demo.pl, menedzer@demo.pl, handlowiec@demo.pl, junior@demo.pl")
    print(f"Hasło: {PW}")


if __name__ == "__main__":
    main()
