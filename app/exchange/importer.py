"""Import pliku w standardzie: odczyt, walidacja wiersz po wierszu, zapis, cofnięcie.

Podgląd i zatwierdzenie wykonują DOKŁADNIE ten sam kod zapisu. Podgląd robi to w
transakcji, którą na końcu wycofuje, więc raport pokazuje wynik bez zgadywania.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Optional

from openpyxl import load_workbook
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import services as svc
from ..models import (
    CONTRACT_STATUSES,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    SELLING_ROLES,
    OFFER_VALID_DAYS,
    Checklist,
    PriceList,
    PriceTemplate,
    Client,
    ClientEvent,
    Notification,
    ClientOffer,
    NipCheck,
    Contract,
    ContractStatusEvent,
    ImportBatch,
    PermissionChange,
    SalesTarget,
    Supplier,
    SupplierRuleSet,
    User,
    UserRate,
)
from ..security import hash_password, new_password
from .standard import SHEETS, STANDARD_VERSION, Col

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ERRORS_SHOWN = 200
RATES_FROM = date(2000, 1, 1)


class ImportError_(Exception):
    """Błąd całego pliku (nie pojedynczego wiersza)."""


class RowError(Exception):
    def __init__(self, column: str, message: str):
        super().__init__(message)
        self.column = column
        self.message = message


@dataclass
class Report:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {"osoby": 0, "spolki": 0, "reguly": 0, "umowy": 0, "zmiany_statusow": 0, "targety": 0, "klienci": 0, "sprawdzenia": 0, "oferty": 0})
    demo: bool = False
    passwords: list[dict] = field(default_factory=list)  # tylko po zatwierdzeniu, nie zapisywane

    def error(self, sheet: str, row: Optional[int], column: str, message: str) -> None:
        self.errors.append({"arkusz": sheet, "wiersz": row, "kolumna": column, "komunikat": message})

    def warn(self, sheet: str, row: Optional[int], column: str, message: str) -> None:
        self.warnings.append({"arkusz": sheet, "wiersz": row, "kolumna": column, "komunikat": message})

    def to_json(self) -> str:
        return json.dumps(
            {"errors": self.errors, "warnings": self.warnings, "counts": self.counts, "demo": self.demo},
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "Report":
        r = cls()
        if text:
            d = json.loads(text)
            r.errors, r.warnings, r.counts, r.demo = d["errors"], d["warnings"], d["counts"], d["demo"]
        return r


# --------------------------------------------------------------------------
# Odczyt wartości komórek
# --------------------------------------------------------------------------

def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _parse(col: Col, raw: Any) -> Any:
    """Zamienia komórkę na wartość albo rzuca RowError z polskim komunikatem."""
    s = _text(raw)
    if s == "":
        if col.required:
            raise RowError(col.name, "uzupełnij to pole")
        return None
    if col.kind in ("text",):
        return s
    if col.kind == "email":
        s = s.lower()
        if "@" not in s or "." not in s.split("@")[-1]:
            raise RowError(col.name, f"niepoprawny adres e-mail „{s}”")
        return s
    if col.kind == "choice":
        for ch in col.choices:
            if s.lower() == str(ch).lower():
                return ch
        raise RowError(col.name, f"wartość „{s}” spoza listy: {', '.join(map(str, col.choices))}")
    if col.kind == "bool":
        if s.lower() in ("tak", "1", "true", "prawda"):
            return True
        if s.lower() in ("nie", "0", "false", "fałsz"):
            return False
        raise RowError(col.name, f"wpisz tak albo nie, jest „{s}”")
    if col.kind in ("dec", "int"):
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            val = Decimal(str(raw))
        else:
            try:
                val = Decimal(s.replace(" ", "").replace(" ", "").replace(",", "."))
            except InvalidOperation:
                raise RowError(col.name, f"to nie jest liczba: „{s}”")
        if not val.is_finite():
            raise RowError(col.name, "to nie jest liczba")
        if col.kind == "int":
            if val != val.to_integral_value():
                raise RowError(col.name, f"podaj liczbę całkowitą, jest „{s}”")
            return int(val)
        return val
    if col.kind == "date":
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        raise RowError(col.name, f"niepoprawna data „{s}”, użyj RRRR-MM-DD albo DD.MM.RRRR")
    raise RowError(col.name, "nieznany typ kolumny")


def read_workbook(content: bytes, report: Report) -> dict[str, list[tuple[int, dict]]]:
    """Zwraca {arkusz: [(numer_wiersza, {kolumna: wartość})]}; błędy dopisuje do raportu."""
    if len(content) > MAX_FILE_BYTES:
        raise ImportError_("Plik jest za duży. Limit to 2 MB.")
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise ImportError_("Nie udało się otworzyć pliku. Wgraj plik Excela w formacie .xlsx.")
    if "README" in wb.sheetnames:
        meta = {}
        for row in wb["README"].iter_rows(min_row=1, max_row=5, values_only=True):
            if row and row[0]:
                meta[_text(row[0]).lower()] = _text(row[1] if len(row) > 1 else "")
        report.demo = meta.get("demo", "nie").lower() == "tak"
        ver = meta.get("standard", "")
        if ver and ver.split(".")[0] != STANDARD_VERSION.split(".")[0]:
            raise ImportError_(f"Plik jest w standardzie {ver}, a platforma obsługuje {STANDARD_VERSION}.")
    data: dict[str, list[tuple[int, dict]]] = {}
    known = [s for s in SHEETS if s in wb.sheetnames]
    if not known:
        raise ImportError_("W pliku nie ma żadnego arkusza ze standardu: " + ", ".join(SHEETS) + ".")
    for extra in wb.sheetnames:
        if extra not in SHEETS and extra != "README":
            report.warn(extra, None, "", "arkusz spoza standardu, pominięty")
    for sheet in known:
        cols = {c.name: c for c in SHEETS[sheet]}
        rows = wb[sheet].iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            continue
        names = [_text(h).lower() for h in header]
        for n in names:
            if n and n not in cols:
                report.warn(sheet, 1, n, "kolumna spoza standardu, pominięta")
        missing = [c.name for c in SHEETS[sheet] if c.required and c.name not in names]
        if missing:
            report.error(sheet, 1, ", ".join(missing), "brakuje wymaganych kolumn")
            continue
        out = []
        for i, raw in enumerate(rows, start=2):
            if raw is None or all(_text(v) == "" for v in raw):
                continue
            values, ok = {}, True
            for idx, n in enumerate(names):
                if n not in cols:
                    continue
                try:
                    values[n] = _parse(cols[n], raw[idx] if idx < len(raw) else None)
                except RowError as e:
                    report.error(sheet, i, e.column, e.message)
                    ok = False
            for c in SHEETS[sheet]:
                values.setdefault(c.name, None)
            if ok:
                out.append((i, values))
        data[sheet] = out
    return data


# --------------------------------------------------------------------------
# Zapis (ten sam kod dla podglądu i zatwierdzenia)
# --------------------------------------------------------------------------

def _row(db: Session, report: Report, sheet: str, rownum: int, fn) -> Any:
    """Każdy wiersz w osobnym punkcie zapisu: błąd wiersza nie psuje pozostałych."""
    sp = db.begin_nested()
    try:
        result = fn()
        sp.commit()
        return result
    except RowError as e:
        sp.rollback()
        report.error(sheet, rownum, e.column, e.message)
    except (svc.BusinessError, eng.EngineError, ValueError) as e:
        sp.rollback()
        report.error(sheet, rownum, "", str(e))
    return None


def _apply(db: Session, data: dict, actor: User, batch: ImportBatch, report: Report) -> None:
    tag = {"import_batch_id": batch.id}
    users_by_email: dict[str, User] = {}

    def user_by_email(email: str) -> Optional[User]:
        return users_by_email.get(email) or db.scalar(select(User).where(User.email == email))

    # 1. Zespół: najpierw menedżerowie, żeby handlowcy mogli ich wskazać.
    team = sorted(data.get("zespol", []), key=lambda r: 0 if r[1]["rola"] == ROLE_MANAGER else 1)
    for rownum, v in team:
        def add_person(v=v):
            if db.scalar(select(User).where(User.email == v["email"])) or v["email"] in users_by_email:
                raise RowError("email", f"osoba z adresem {v['email']} już istnieje")
            manager_id = None
            if v["menedzer_email"]:
                m = user_by_email(v["menedzer_email"])
                if not m or m.role != ROLE_MANAGER:
                    raise RowError("menedzer_email", f"{v['menedzer_email']} nie jest menedżerem w pliku ani w platformie")
                if v["rola"] == "bok":
                    raise RowError("menedzer_email", "biuro obsługi nie należy do zespołu menedżera")
                manager_id = m.id
            sells = v["rola"] in SELLING_ROLES
            if sells and v["udzial_w_narzucie_proc"] is None:
                raise RowError("udzial_w_narzucie_proc", "udział w narzucie jest wymagany dla menedżera i handlowca")
            for key in ("udzial_w_narzucie_proc", "override_proc"):
                if v[key] is not None and not (0 <= v[key] <= 100):
                    raise RowError(key, "procent musi być w zakresie 0–100")
            if len(v["imie"]) < 2 or len(v["nazwisko"]) < 2:
                raise RowError("nazwisko", "imię i nazwisko muszą mieć co najmniej 2 znaki")
            password = new_password()
            u = User(
                email=v["email"], password_hash=hash_password(password), role=v["rola"],
                manager_id=manager_id, active=True if v["aktywny"] is None else v["aktywny"],
                ext_id=v["id_zewn"], **tag,
            )
            u.set_names(v["imie"], v["nazwisko"])
            db.add(u)
            db.flush()
            if sells:
                db.add(UserRate(
                    user_id=u.id, valid_from=RATES_FROM, trader_share_pct=v["udzial_w_narzucie_proc"],
                    override_pct=(v["override_proc"] or Decimal(0)) if u.role == ROLE_MANAGER else Decimal(0),
                    override_base=v["baza_override"] or eng.OVERRIDE_OD_NARZUTU,
                ))
                db.flush()
            users_by_email[u.email] = u
            report.passwords.append({"name": u.name, "email": u.email, "role": u.role_label, "password": password})
            report.counts["osoby"] += 1
        _row(db, report, "zespol", rownum, add_person)

    # 2. Spółki i reguły.
    suppliers: dict[str, Supplier] = {}
    for rownum, v in data.get("spolki", []):
        def add_rules(v=v):
            key = v["nazwa"].lower()
            s = suppliers.get(key)
            if s is None:
                existing = db.scalar(select(Supplier).where(Supplier.name == v["nazwa"]))
                if existing:
                    raise RowError("nazwa", f"spółka {v['nazwa']} już jest w platformie; jej reguły zmień w zakładce Spółki")
                s = Supplier(name=v["nazwa"], active=True if v["aktywna"] is None else v["aktywna"], ext_id=v["id_zewn"], **tag)
                db.add(s)
                db.flush()
                suppliers[key] = s
                report.counts["spolki"] += 1
            for k in ("udzial_brokera_proc", "pierwsza_transza_proc"):
                if not (0 <= v[k] <= 100):
                    raise RowError(k, "procent musi być w zakresie 0–100")
            if any(r.valid_from == v["obowiazuje_od"] for r in s.rule_sets):
                raise RowError("obowiazuje_od", f"spółka {s.name} ma już reguły od tego dnia")
            rs = SupplierRuleSet(
                supplier_id=s.id, valid_from=v["obowiazuje_od"], broker_share_pct=v["udzial_brokera_proc"],
                first_tranche_pct=v["pierwsza_transza_proc"],
                first_tranche_trigger=v["wyzwalacz_transzy"] or "weryfikacja",
                max_markup_pln_mwh=v["limit_narzutu_zl_mwh"],
                new_connection_months=12 if v["nowe_przylacza_miesiace"] is None else v["nowe_przylacza_miesiace"],
                clawback_mode=v["tryb_korekty"] or eng.KOREKTA_PROPORCJONALNA,
                note=v["uwagi"] or "", ext_id=v["id_zewn"], **tag,
            )
            db.add(rs)
            s.rule_sets.append(rs)
            db.flush()
            report.counts["reguly"] += 1
        _row(db, report, "spolki", rownum, add_rules)

    # 3. Umowy z historią statusów.
    history: dict[str, list[tuple[int, dict]]] = {}
    for rownum, v in data.get("historia_statusow", []):
        history.setdefault(v["umowa_id_zewn"], []).append((rownum, v))
    contract_ids = {v["id_zewn"] for _, v in data.get("umowy", [])}
    for ext, rows in history.items():
        if ext not in contract_ids:
            for rownum, _ in rows:
                report.error("historia_statusow", rownum, "umowa_id_zewn", f"brak umowy {ext} w arkuszu umowy")
    seen: set[str] = set()
    for rownum, v in data.get("umowy", []):
        def add_contract(v=v):
            if v["id_zewn"] in seen:
                raise RowError("id_zewn", f"umowa {v['id_zewn']} występuje w pliku dwa razy")
            seen.add(v["id_zewn"])
            if db.scalar(select(Contract).where(Contract.ext_id == v["id_zewn"])):
                raise RowError("id_zewn", f"umowa {v['id_zewn']} była już zaimportowana")
            supplier = suppliers.get(v["spolka"].lower()) or db.scalar(select(Supplier).where(Supplier.name == v["spolka"]))
            if not supplier:
                raise RowError("spolka", f"nie ma spółki {v['spolka']} w pliku ani w platformie")
            trader = user_by_email(v["handlowiec_email"])
            if not trader:
                raise RowError("handlowiec_email", f"nie ma osoby {v['handlowiec_email']} w pliku ani w platformie")
            nip = "".join(ch for ch in (v["klient_nip"] or "") if ch in "0123456789")
            if nip and not svc_valid_nip(nip):
                raise RowError("klient_nip", "NIP ma niepoprawną sumę kontrolną")
            steps = sorted(history.get(v["id_zewn"], []), key=lambda r: (r[1]["data_zdarzenia"], r[0]))
            first_status = steps[0][1]["status"] if steps else v["status"]
            c = svc.build_contract(
                db, actor=actor, trader=trader, supplier=supplier, client_name=v["klient_nazwa"],
                client_nip=nip, medium=v["medium"], signed_date=v["data_podpisania"],
                start_date=v["start_dostaw"], term_months=v["okres_miesiace"],
                annual_volume_mwh=v["wolumen_roczny_mwh"], markup_pln_mwh=v["narzut_zl_mwh"],
                base_price_pln_mwh=v["cena_bazowa_zl_mwh"], new_connection=bool(v["nowe_przylacze"]),
                status=first_status, initial_note=f"Zaimportowano z pliku {batch.filename}.",
            )
            c.ext_id, c.import_batch_id = v["id_zewn"], batch.id
            frozen = {
                "udzial_brokera_proc": "broker_share_pct", "pierwsza_transza_proc": "first_tranche_pct",
                "udzial_handlowca_proc": "trader_share_pct", "override_menedzera_proc": "manager_override_pct",
            }
            for col, attr in frozen.items():
                if v[col] is not None:
                    if not (0 <= v[col] <= 100):
                        raise RowError(col, "procent musi być w zakresie 0–100")
                    setattr(c, attr, v[col])
            svc.calculate_contract(c)  # walidacja silnikiem po nadpisaniu warunków
            if steps:
                first_date = steps[0][1]["data_zdarzenia"]
                c.events[0].effective_date = first_date
                c.events[0].note = (steps[0][1]["notatka"] or "") or c.events[0].note
            for srow, step in steps[1:]:
                try:
                    svc.apply_status_change(
                        db, actor=actor, c=c, new_status=step["status"],
                        effective_date=step["data_zdarzenia"], note=step["notatka"] or "",
                    )
                except svc.BusinessError as e:
                    raise RowError("historia_statusow", f"wiersz {srow} historii: {e}")
                report.counts["zmiany_statusow"] += 1
            if c.status != v["status"]:
                raise RowError("status", f"status „{v['status']}” nie zgadza się z ostatnim wpisem historii „{c.status}”")
            db.flush()
            report.counts["umowy"] += 1
        _row(db, report, "umowy", rownum, add_contract)

    # 4. Targety miesięczne (arkusz opcjonalny). Istniejący target na ten miesiąc zostaje nadpisany.
    for rownum, v in data.get("targety", []):
        def add_target(v=v):
            person = user_by_email(v["email"])
            if not person:
                raise RowError("email", f"nie ma osoby {v['email']} w pliku ani w platformie")
            if person.role not in (ROLE_MANAGER, ROLE_TRADER):
                raise RowError("email", "target można ustawić tylko menedżerowi albo handlowcowi")
            month = svc.parse_month(v["miesiac"][:7])  # Excel potrafi zamienić 2026-11 na datę
            if not month:
                raise RowError("miesiac", f"niepoprawny miesiąc „{v['miesiac']}”, użyj RRRR-MM")
            if v["kwota_zl"] < 0:
                raise RowError("kwota_zl", "target nie może być ujemny")
            t = db.scalar(select(SalesTarget).where(SalesTarget.user_id == person.id, SalesTarget.month == month))
            if t:
                t.amount, t.set_by_id = v["kwota_zl"], actor.id
            else:
                db.add(SalesTarget(user_id=person.id, month=month, amount=v["kwota_zl"], set_by_id=actor.id))
            db.flush()
            report.counts["targety"] += 1
        _row(db, report, "targety", rownum, add_target)

    # 5. Klienci w lejku, sprawdzenia NIP przez BOK i oferty.
    clients: dict[str, Client] = {}
    for rownum, v in data.get("klienci", []):
        def add_client(v=v):
            if v["id_zewn"] in clients or db.scalar(select(Client).where(Client.ext_id == v["id_zewn"])):
                raise RowError("id_zewn", f"klient {v['id_zewn']} występuje dwa razy albo był już zaimportowany")
            owner = user_by_email(v["handlowiec_email"])
            if not owner or owner.role not in SELLING_ROLES:
                raise RowError("handlowiec_email", f"nie ma osoby sprzedającej {v['handlowiec_email']}")
            nip = "".join(ch for ch in (v["nip"] or "") if ch in "0123456789")
            if nip and not svc_valid_nip(nip):
                raise RowError("nip", "NIP ma niepoprawną sumę kontrolną")
            if nip and db.scalar(select(Client).where(Client.nip == nip)):
                raise RowError("nip", "klient z tym NIP-em już jest w platformie")
            stage = v["etap"] or "lead"
            if stage == "przegrana" and not v["powod_przegranej"]:
                raise RowError("powod_przegranej", "przy przegranej podaj powód")
            c = Client(
                name=v["nazwa"][:300], nip=nip or None, contact_person=(v["osoba_kontaktowa"] or "")[:200],
                phone=(v["telefon"] or "")[:50], email=(v["email"] or "")[:200], source=v["zrodlo"] or "",
                owner_id=owner.id, stage=stage, stage_since=date.today(), next_step=(v["nastepny_krok"] or "")[:300],
                next_step_date=v["nastepny_krok_data"], lost_reason=v["powod_przegranej"] or "", ext_id=v["id_zewn"], **tag,
            )
            db.add(c)
            db.flush()
            db.add(ClientEvent(client_id=c.id, kind="system", text=(f"Zaimportowano z pliku {batch.filename}. " + (v["notatka"] or "")).strip()))
            clients[v["id_zewn"]] = c
            report.counts["klienci"] += 1
        _row(db, report, "klienci", rownum, add_client)

    def client_of(ext: str) -> Client:
        c = clients.get(ext) or db.scalar(select(Client).where(Client.ext_id == ext))
        if not c:
            raise RowError("klient_id_zewn", f"brak klienta {ext} w arkuszu klienci")
        return c

    def supplier_of(name: str) -> Supplier:
        s = suppliers.get(name.lower()) or db.scalar(select(Supplier).where(Supplier.name == name))
        if not s:
            raise RowError("spolka", f"nie ma spółki {name} w pliku ani w platformie")
        return s

    for rownum, v in data.get("sprawdzenia_nip", []):
        def add_check(v=v):
            c, s = client_of(v["klient_id_zewn"]), supplier_of(v["spolka"])
            if not c.nip:
                raise RowError("klient_id_zewn", "klient bez NIP-u nie może mieć sprawdzenia w BOK")
            done = v["wynik"] != "do_sprawdzenia"
            db.add(NipCheck(
                client_id=c.id, supplier_id=s.id, result=v["wynik"], note=(v["uwagi"] or "")[:500],
                reserved_until=v["zarezerwowany_do"] if v["wynik"] == "zarezerwowany" else None,
                requested_by_id=c.owner_id, checked_at=datetime.utcnow() if done else None,
            ))
            db.flush()
            report.counts["sprawdzenia"] += 1
        _row(db, report, "sprawdzenia_nip", rownum, add_check)

    for rownum, v in data.get("oferty", []):
        def add_client_offer(v=v):
            c, s = client_of(v["klient_id_zewn"]), supplier_of(v["spolka"])
            sent = v["data_wyslania"]
            db.add(ClientOffer(
                client_id=c.id, supplier_id=s.id, pricing_product=v["produkt"] or "fix", medium=v["medium"] or "energia",
                base_price_pln_mwh=v["cena_bazowa_zl_mwh"], markup_pln_mwh=v["marza_zl_mwh"],
                annual_volume_mwh=v["wolumen_roczny_mwh"], term_months=v["okres_miesiace"], sent_date=sent,
                valid_until=v["wazna_do"] or sent + timedelta(days=OFFER_VALID_DAYS), status=v["status"] or "otwarta",
                created_by_id=c.owner_id,
            ))
            db.add(ClientEvent(client_id=c.id, kind="oferta", day=sent, user_id=c.owner_id,
                               text=f"Oferta {s.name}, marża {v['marza_zl_mwh']} zł/MWh."))
            db.flush()
            report.counts["oferty"] += 1
        _row(db, report, "oferty", rownum, add_client_offer)

    # 6. Dane demonstracyjne: cenniki spółek (ceny fikcyjne), żeby dało się sprawdzić kalkulator.
    if report.demo and suppliers:
        from .demo import seed_price_lists
        report.counts["cenniki"] = seed_price_lists(db, actor, list({s.id: s for s in suppliers.values()}.values()), date.today())


def svc_valid_nip(nip: str) -> bool:
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    if len(nip) != 10 or not (nip.isascii() and nip.isdigit()):
        return False
    check = sum(int(d) * w for d, w in zip(nip, weights)) % 11
    return check != 10 and check == int(nip[9])


# --------------------------------------------------------------------------
# Operacje na paczkach
# --------------------------------------------------------------------------

def preview(db: Session, *, actor: User, filename: str, content: bytes) -> ImportBatch:
    """Tworzy paczkę w stanie „podgląd” z raportem. Dane nie zostają zapisane."""
    batch = ImportBatch(filename=filename[:300], status="podglad", created_by_id=actor.id, content=content)
    db.add(batch)
    db.commit()
    report = Report()
    try:
        data = read_workbook(content, report)
        tx = db.begin_nested()
        try:
            _apply(db, data, actor, batch, report)
        finally:
            tx.rollback()
    except ImportError_ as e:
        report.error("plik", None, "", str(e))
    db.expire_all()
    batch = db.get(ImportBatch, batch.id)
    batch.is_demo = report.demo
    batch.summary = report.to_json()
    db.commit()
    return batch


def commit(db: Session, *, actor: User, batch: ImportBatch) -> Report:
    """Zapisuje paczkę. Przy jakimkolwiek błędzie nic nie zostaje zapisane."""
    if batch.status != "podglad" or not batch.content:
        raise svc.BusinessError("Tej paczki nie można już zatwierdzić.")
    report = Report()
    data = read_workbook(batch.content, report)
    _apply(db, data, actor, batch, report)
    if report.errors:
        db.rollback()
        raise svc.BusinessError("Plik ma błędy. Nic nie zostało zapisane. Wróć do raportu.")
    batch.status = "zatwierdzony"
    batch.applied_at = datetime.utcnow()
    batch.content = None
    batch.summary = report.to_json()
    db.commit()
    return report


def reject(db: Session, batch: ImportBatch) -> None:
    if batch.status == "podglad":
        batch.status = "odrzucony"
        batch.content = None
        db.commit()


def blockers(db: Session, batch: ImportBatch) -> list[str]:
    """Powody, dla których paczki nie da się cofnąć bez naruszenia innych danych."""
    bid = batch.id
    users = select(User.id).where(User.import_batch_id == bid)
    sups = select(Supplier.id).where(Supplier.import_batch_id == bid)
    rules = select(SupplierRuleSet.id).where(SupplierRuleSet.import_batch_id == bid)
    foreign = Contract.import_batch_id.is_(None) | (Contract.import_batch_id != bid)
    out = []
    n = db.query(Contract).filter(foreign, or_(
        Contract.trader_id.in_(users), Contract.manager_id.in_(users),
        Contract.supplier_id.in_(sups), Contract.rule_set_id.in_(rules), Contract.created_by_id.in_(users),
    )).count()
    if n:
        out.append(f"{n} umów spoza tej paczki korzysta z jej osób albo spółek")
    n = db.query(Client).filter(
        Client.import_batch_id.is_(None) | (Client.import_batch_id != bid), Client.owner_id.in_(users)
    ).count()
    if n:
        out.append(f"{n} klientów spoza tej paczki ma opiekuna z tej paczki")
    foreign_client = Client.import_batch_id.is_(None) | (Client.import_batch_id != bid)
    n = db.query(NipCheck).join(Client).filter(foreign_client, NipCheck.supplier_id.in_(sups)).count()
    n += db.query(ClientOffer).join(Client).filter(foreign_client, ClientOffer.supplier_id.in_(sups)).count()
    if n:
        out.append(f"{n} sprawdzeń NIP albo ofert spoza tej paczki dotyczy jej spółek")
    n = db.query(User).filter(
        User.import_batch_id.is_(None) | (User.import_batch_id != bid), User.manager_id.in_(users)
    ).count()
    if n:
        out.append(f"{n} osób spoza tej paczki ma w niej swojego menedżera")
    n = db.query(SupplierRuleSet).filter(
        SupplierRuleSet.import_batch_id.is_(None) | (SupplierRuleSet.import_batch_id != bid),
        SupplierRuleSet.supplier_id.in_(sups),
    ).count()
    if n:
        out.append(f"{n} reguł prowizji dodanych ręcznie do spółek z tej paczki")
    return out


def revert(db: Session, batch: ImportBatch) -> dict:
    """Usuwa wszystkie rekordy paczki. Odmawia, gdy inne dane z nich korzystają."""
    if batch.status != "zatwierdzony":
        raise svc.BusinessError("Cofnąć można tylko zatwierdzony import.")
    why = blockers(db, batch)
    if why:
        raise svc.BusinessError("Nie można cofnąć importu: " + "; ".join(why) + ".")
    bid = batch.id
    user_ids = list(db.scalars(select(User.id).where(User.import_batch_id == bid)))
    counts = {"umowy": 0, "osoby": 0, "spolki": 0}
    # wpisy historii i uprawnień zrobione przez usuwane osoby na innych danych zostają, bez autora
    if user_ids:
        db.execute(update(ContractStatusEvent).where(ContractStatusEvent.changed_by_id.in_(user_ids)).values(changed_by_id=None))
        db.execute(update(PermissionChange).where(PermissionChange.changed_by_id.in_(user_ids)).values(changed_by_id=None))
        db.execute(update(SalesTarget).where(SalesTarget.set_by_id.in_(user_ids)).values(set_by_id=None))
        for t in db.scalars(select(SalesTarget).where(SalesTarget.user_id.in_(user_ids))):
            db.delete(t)
        db.execute(update(NipCheck).where(NipCheck.requested_by_id.in_(user_ids)).values(requested_by_id=None))
        db.execute(update(NipCheck).where(NipCheck.checked_by_id.in_(user_ids)).values(checked_by_id=None))
        db.execute(update(ClientOffer).where(ClientOffer.created_by_id.in_(user_ids)).values(created_by_id=None))
        db.execute(update(ClientEvent).where(ClientEvent.user_id.in_(user_ids)).values(user_id=None))
        db.execute(update(Notification).where(Notification.recipient_id.in_(user_ids)).values(recipient_id=None))
        db.execute(update(Notification).where(Notification.actor_id.in_(user_ids)).values(actor_id=None))
        db.execute(update(Checklist).where(Checklist.updated_by_id.in_(user_ids)).values(updated_by_id=None))
        db.execute(update(PriceList).where(PriceList.created_by_id.in_(user_ids)).values(created_by_id=None))
        db.execute(update(PriceList).where(PriceList.approved_by_id.in_(user_ids)).values(approved_by_id=None))
        db.execute(update(PriceTemplate).where(PriceTemplate.updated_by_id.in_(user_ids)).values(updated_by_id=None))
    counts["klienci"] = 0
    for cl in db.scalars(select(Client).where(Client.import_batch_id == bid)):
        db.delete(cl)
        counts["klienci"] += 1
    db.flush()
    for c in db.scalars(select(Contract).where(Contract.import_batch_id == bid)):
        db.delete(c)
        counts["umowy"] += 1
    db.flush()
    batch_users = list(db.scalars(select(User).where(User.import_batch_id == bid)))
    for u in batch_users:
        u.manager_id = None
    db.flush()
    for u in batch_users:
        db.delete(u)
        counts["osoby"] += 1
    db.flush()
    batch_sups = select(Supplier.id).where(Supplier.import_batch_id == bid)
    for pl_ in db.scalars(select(PriceList).where(PriceList.supplier_id.in_(batch_sups))):
        db.delete(pl_)  # cenniki spółek z paczki znikają razem ze spółkami
    for t in db.scalars(select(PriceTemplate).where(PriceTemplate.supplier_id.in_(batch_sups))):
        db.delete(t)
    db.flush()
    for s in db.scalars(select(Supplier).where(Supplier.import_batch_id == bid)):
        db.delete(s)
        counts["spolki"] += 1
    batch.status = "cofniety"
    batch.reverted_at = datetime.utcnow()
    db.commit()
    return counts


def demo_active(db: Session) -> bool:
    return db.scalar(
        select(ImportBatch.id).where(ImportBatch.is_demo.is_(True), ImportBatch.status == "zatwierdzony").limit(1)
    ) is not None


def demo_suppliers_without_prices(db: Session) -> list[Supplier]:
    """Spółki z aktywnej paczki demo, które nie mają jeszcze żadnej struktury cennika."""
    ids = list(db.scalars(select(ImportBatch.id).where(ImportBatch.is_demo.is_(True), ImportBatch.status == "zatwierdzony")))
    if not ids:
        return []
    have = select(PriceTemplate.supplier_id)
    return list(db.scalars(
        select(Supplier).where(Supplier.import_batch_id.in_(ids), Supplier.id.not_in(have)).order_by(Supplier.name)
    ))


def _demo_supplier_ids(db: Session) -> list[int]:
    ids = list(db.scalars(select(ImportBatch.id).where(ImportBatch.is_demo.is_(True), ImportBatch.status == "zatwierdzony")))
    return list(db.scalars(select(Supplier.id).where(Supplier.import_batch_id.in_(ids)))) if ids else []


def demo_suppliers_with_prices(db: Session) -> int:
    ids = _demo_supplier_ids(db)
    return db.scalar(select(func.count(PriceTemplate.id)).where(PriceTemplate.supplier_id.in_(ids))) if ids else 0


def add_demo_price_lists(db: Session, actor: User, replace: bool = False) -> int:
    """Dopisuje cenniki demo (ceny fikcyjne) spółkom demo, które ich nie mają. Nie rusza reszty danych;
    cofnięcie paczki demo usuwa je razem ze spółkami. replace=True najpierw usuwa istniejące cenniki
    spółek demo (tylko demo, nigdy innych spółek) i tworzy je od nowa w bieżącym wzorze."""
    from .demo import seed_price_lists

    if replace:
        ids = _demo_supplier_ids(db)
        for pl_ in db.scalars(select(PriceList).where(PriceList.supplier_id.in_(ids))):
            db.delete(pl_)
        for t in db.scalars(select(PriceTemplate).where(PriceTemplate.supplier_id.in_(ids))):
            db.delete(t)
        db.flush()
    suppliers = demo_suppliers_without_prices(db)
    if not suppliers:
        return 0
    n = seed_price_lists(db, actor, suppliers, date.today())
    db.commit()
    return n


__all__ = ["demo_suppliers_with_prices", "demo_suppliers_without_prices", "add_demo_price_lists", "preview", "commit", "reject", "revert", "blockers", "demo_active", "Report", "ROLE_OWNER", "CONTRACT_STATUSES"]
