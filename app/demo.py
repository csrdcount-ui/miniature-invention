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
from .models import ROLE_MANAGER, ROLE_OWNER, ROLE_TRADER, Supplier, SupplierRuleSet, User, UserRate
from .security import hash_password

PW = "demo-haslo-123"
START = date(2000, 1, 1)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            print("Baza nie jest pusta — pomijam dane demo.")
            return
        h = hash_password(PW)
        owner = User(email="wlasciciel@demo.pl", name="Właściciel Demo", password_hash=h, role=ROLE_OWNER)
        mgr = User(email="menedzer@demo.pl", name="Marta Menedżer", password_hash=h, role=ROLE_MANAGER)
        db.add_all([owner, mgr])
        db.flush()
        t1 = User(email="handlowiec@demo.pl", name="Tomasz Handlowiec", password_hash=h, role=ROLE_TRADER, manager_id=mgr.id)
        t2 = User(email="junior@demo.pl", name="Julia Junior", password_hash=h, role=ROLE_TRADER, manager_id=mgr.id)
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

        today = date.today()

        def ago(months: int) -> date:
            y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
            return date(y, m + 1, 1)

        created = []
        for trader, sup, client, vol, months, markup, new, signed, start in [
            (t1, a, "Piekarnia Złoty Kłos", 100, 60, 100, False, ago(14), ago(12)),
            (t1, b, "Chłodnia Lubelska", 850, 36, 85, False, ago(5), ago(3)),
            (t2, a, "Hotel Pod Lipami", 240, 24, 120, False, ago(1), None),
            (t2, b, "Nowa Hala Logistyczna", 600, 48, 90, True, today, None),
            (mgr, a, "Zakład Mechaniczny Kowalski", 1200, 36, 70, False, today, None),
        ]:
            created.append(svc.create_contract(
                db, actor=owner, trader=trader, supplier=sup, client_name=client, client_nip="", medium="energia",
                signed_date=signed, start_date=start, term_months=months,
                annual_volume_mwh=Decimal(vol), markup_pln_mwh=Decimal(markup), base_price_pln_mwh=Decimal(480),
                new_connection=new, status="Umowa podpisana",
            ))

        # Rejestr: pierwsze transze od spółek, jedna wypłata dla zespołu już rozliczona.
        from . import settlements as st

        for c in created[:3]:
            b = svc.calculate_contract(c)
            e = st.record_entry(db, actor=owner, contract=c, kind="transza1",
                                booked_on=(c.start_date or today), amount=b.broker.tranche1,
                                note="Zestawienie prowizyjne, dane demo")
            if c is created[0]:
                st.mark_paid(db, actor=owner, entry=e, who="handlowiec", paid_on=c.start_date)
                st.mark_paid(db, actor=owner, entry=e, who="menedzer", paid_on=c.start_date)
    print("Dane demo utworzone. Konta: wlasciciel@demo.pl, menedzer@demo.pl, handlowiec@demo.pl, junior@demo.pl")
    print(f"Hasło: {PW}")


if __name__ == "__main__":
    main()
