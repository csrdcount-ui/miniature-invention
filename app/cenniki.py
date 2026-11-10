"""Cenniki spółek i kalkulator oferty. Bez FastAPI i bez warstwy stron.

Ustalenia z właścicielką (10.11.2026):
- ceny wpisuje BOK w formularzu spółki, projekt zatwierdza; kalkulator czyta tylko zatwierdzone;
- nowy cennik kończy poprzedni z końcem dnia swojego startu;
- okresy: pojedyncze lata (średnia ważona liczbą miesięcy umowy w każdym roku) albo gotowe
  bloki lat („2027-2029”), które wygrywają, gdy dokładnie pokrywają okres umowy;
- handlowiec może dodać inną marżę do każdej strefy;
- opłata handlowa: stała albo bazowa z dopłatą handlowca (dodatkowy przychód) — zależnie od spółki;
- gwarancje pochodzenia, wycena indywidualna i oferty specjalne: osobne procesy, później.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine as eng
from . import services as svc
from .models import (
    OH_MODES,
    PRICE_PRODUCTS,
    PriceItem,
    PriceList,
    PriceTemplate,
    Supplier,
    User,
)

BusinessError = svc.BusinessError
STALE_DAYS = 7  # cennik starszy niż tydzień: ostrzeżenie dla BOK i handlowca


# --------------------------------------------------------------------------
# Szablon: okresy i podział
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Period:
    label: str
    first: int
    last: int

    @property
    def is_block(self) -> bool:
        return self.last > self.first


@dataclass(frozen=True)
class Segment:
    key: str  # grupa taryfowa („C12a”) albo przedział („0-300”)
    zones: int  # liczba stref (przedział wolumenu: 1)
    low: Optional[Decimal] = None
    high: Optional[Decimal] = None

    @property
    def label(self) -> str:
        if self.low is None:
            return self.key
        return f"{self.low.normalize():f}–{self.high.normalize():f} MWh rocznie"


def parse_periods(text: str) -> list[Period]:
    out = []
    for raw in (text or "").replace(";", ",").split(","):
        raw = raw.strip().replace("–", "-").replace(" ", "")
        if not raw:
            continue
        parts = raw.split("-")
        try:
            years = [int(p) for p in parts]
        except ValueError:
            raise BusinessError(f"Okres „{raw}”: wpisz rok, np. 2026, albo blok lat, np. 2027-2029.")
        if len(years) == 1:
            years.append(years[0])
        if len(years) != 2 or not (2000 <= years[0] <= years[1] <= 2100):
            raise BusinessError(f"Okres „{raw}”: wpisz rok, np. 2026, albo blok lat, np. 2027-2029.")
        label = str(years[0]) if years[0] == years[1] else f"{years[0]}-{years[1]}"
        out.append(Period(label, years[0], years[1]))
    if not out:
        raise BusinessError("Podaj co najmniej jeden okres, np. 2026, 2027 albo 2027-2029.")
    if len({p.label for p in out}) != len(out):
        raise BusinessError("Okresy się powtarzają.")
    return sorted(out, key=lambda p: (p.first, p.last))


def parse_segments(split: str, text: str) -> list[Segment]:
    out = []
    for raw in (text or "").replace(";", ",").split(","):
        raw = raw.strip()
        if not raw:
            continue
        if split == "grupy":
            code, _, zones = raw.partition(":")
            code = code.strip()
            try:
                z = int(zones.strip() or 1)
            except ValueError:
                raise BusinessError(f"Grupa „{raw}”: po dwukropku wpisz liczbę stref, np. C12a:2.")
            if not code or not 1 <= z <= 3:
                raise BusinessError(f"Grupa „{raw}”: liczba stref od 1 do 3, np. C12a:2.")
            out.append(Segment(code, z))
        else:
            lo, _, hi = raw.replace("–", "-").replace(" ", "").partition("-")
            try:
                low, high = Decimal(lo.replace(",", ".")), Decimal(hi.replace(",", "."))
            except InvalidOperation:
                raise BusinessError(f"Przedział „{raw}”: wpisz od-do w MWh, np. 0-300.")
            if low < 0 or high <= low:
                raise BusinessError(f"Przedział „{raw}”: koniec musi być większy od początku.")
            out.append(Segment(f"{low.normalize():f}-{high.normalize():f}", 1, low, high))
    if not out:
        raise BusinessError("Podaj grupy taryfowe (np. C11:1, C12a:2) albo przedziały wolumenu (np. 0-300, 300-1000).")
    if len({s.key for s in out}) != len(out):
        raise BusinessError("Grupy albo przedziały się powtarzają.")
    if split == "wolumen":
        out.sort(key=lambda s: s.low)
    return out


def products_of(tpl: PriceTemplate) -> list[str]:
    return [p for p in (tpl.products or "").split(",") if p in PRICE_PRODUCTS]


def save_template(db: Session, supplier: Supplier, user: User, *, products: list[str], periods: str, split: str,
                  segments: str, oh_mode: str, max_volume: Optional[Decimal], individual_from: Optional[Decimal],
                  note: str = "") -> PriceTemplate:
    products = [p for p in products if p in PRICE_PRODUCTS]
    if not products:
        raise BusinessError("Zaznacz co najmniej jeden produkt.")
    if split not in ("grupy", "wolumen"):
        raise BusinessError("Wybierz, od czego zależy cena: grupy taryfowe albo wolumen.")
    if oh_mode not in OH_MODES:
        raise BusinessError("Wybierz rodzaj opłaty handlowej.")
    pers = parse_periods(periods)
    segs = parse_segments(split, segments)
    tpl = db.scalar(select(PriceTemplate).where(PriceTemplate.supplier_id == supplier.id))
    if not tpl:
        tpl = PriceTemplate(supplier_id=supplier.id)
        db.add(tpl)
    tpl.products = ",".join(products)
    tpl.periods = ", ".join(p.label for p in pers)
    tpl.split = split
    tpl.segments = ", ".join(f"{s.key}:{s.zones}" if split == "grupy" else s.key for s in segs)
    tpl.oh_mode, tpl.max_volume_mwh, tpl.individual_from_mwh = oh_mode, max_volume, individual_from
    tpl.note, tpl.updated_by_id, tpl.updated_at = note.strip()[:2000], user.id, datetime.utcnow()
    db.flush()
    return tpl


# --------------------------------------------------------------------------
# Formularz cennika dla BOK
# --------------------------------------------------------------------------

def price_key(product: str, period: str, segment: str, zone: int) -> str:
    return f"c|{product}|{period}|{segment}|{zone}"


def oh_key(segment: str) -> str:
    return f"oh|{segment}"


def zone_label(zones: int, z: int, cap: bool = False) -> str:
    text = "całodobowa" if zones == 1 else f"strefa {['I', 'II', 'III'][z - 1]}"
    return text[:1].upper() + text[1:] if cap else text


def form_sections(tpl: PriceTemplate) -> dict:
    """Pola formularza w kolejności: produkt → okres → grupa/przedział → strefy, potem OH."""
    pers = parse_periods(tpl.periods)
    segs = parse_segments(tpl.split, tpl.segments)
    sections = []
    for prod in products_of(tpl):
        for per in pers:
            rows = []
            for seg in segs:
                fields = [{
                    "key": price_key(prod, per.label, seg.key, z),
                    "label": f"{per.label}, {seg.label}, {zone_label(seg.zones, z)}, zł/MWh",
                    "short": zone_label(seg.zones, z),
                } for z in range(1, seg.zones + 1)]
                rows.append({"segment": seg, "fields": fields})
            sections.append({"title": f"{PRICE_PRODUCTS[prod]}: {per.label}", "rows": rows, "product": prod, "period": per})
    oh = [{"key": oh_key(seg.key), "label": f"Opłata handlowa, {seg.label}, zł na miesiąc za punkt poboru"} for seg in segs]
    return {"sections": sections, "oh": oh}


def values_of(pl: Optional[PriceList]) -> dict[str, str]:
    if not pl:
        return {}
    out = {}
    for it in pl.items:
        key = oh_key(it.segment) if it.kind == "oh" else price_key(it.product, it.period, it.segment, it.zone)
        out[key] = f"{it.value.normalize():f}".replace(".", ",")
    return out


def _dec(raw) -> Optional[Decimal]:
    s = str(raw or "").strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise ValueError(s)
    if not v.is_finite():
        raise ValueError(s)
    return v


def save_draft(db: Session, supplier: Supplier, user: User, form: dict, *, valid_from: date,
               valid_to: Optional[date], note: str = "", draft: Optional[PriceList] = None) -> PriceList:
    tpl = template_of(db, supplier.id)
    if not tpl:
        raise BusinessError("Najpierw ustaw budowę cennika tej spółki.")
    if valid_to and valid_to < valid_from:
        raise BusinessError("Data końca cennika nie może być wcześniejsza niż data startu.")
    secs = form_sections(tpl)
    items, errors, filled = [], [], 0
    for sec in secs["sections"]:
        for row in sec["rows"]:
            for f in row["fields"]:
                try:
                    v = _dec(form.get(f["key"]))
                except ValueError:
                    errors.append(f"{f['label']}: to nie jest liczba")
                    continue
                if v is None:
                    continue
                if not Decimal("-1000") <= v <= Decimal("10000"):
                    errors.append(f"{f['label']}: wartość poza zakresem")
                    continue
                _, prod, per, seg, z = f["key"].split("|")
                items.append(PriceItem(kind="cena", product=prod, period=per, segment=seg, zone=int(z), value=v))
                filled += 1
    for f in secs["oh"]:
        try:
            v = _dec(form.get(f["key"]))
        except ValueError:
            errors.append(f"{f['label']}: to nie jest liczba")
            continue
        if v is not None:
            if v < 0:
                errors.append(f"{f['label']}: opłata nie może być ujemna")
                continue
            items.append(PriceItem(kind="oh", product="", period="", segment=f["key"].split("|", 1)[1], zone=0, value=v))
    if errors:
        raise BusinessError("Popraw pola: " + "; ".join(errors[:10]) + ("…" if len(errors) > 10 else "."))
    if not filled:
        raise BusinessError("Cennik nie ma żadnej ceny. Wpisz ceny albo zostaw poprzedni cennik.")
    if draft is None:
        draft = PriceList(supplier_id=supplier.id, created_by_id=user.id)
        db.add(draft)
    else:
        draft.items.clear()
    draft.status, draft.valid_from, draft.valid_to, draft.note = "projekt", valid_from, valid_to, note.strip()[:500]
    draft.items.extend(items)
    db.flush()
    return draft


def approve(db: Session, pl: PriceList, user: User) -> None:
    if pl.status != "projekt":
        raise BusinessError("Ten cennik jest już zatwierdzony.")
    pl.status, pl.approved_by_id, pl.approved_at = "zatwierdzony", user.id, datetime.utcnow()
    # poprzednie cenniki spółki działają do końca dnia startu nowego
    for old in db.scalars(select(PriceList).where(
        PriceList.supplier_id == pl.supplier_id, PriceList.status == "zatwierdzony", PriceList.id != pl.id,
        PriceList.valid_from <= pl.valid_from,
    )):
        if old.valid_to is None or old.valid_to > pl.valid_from:
            old.valid_to = pl.valid_from
    db.flush()


def template_of(db: Session, supplier_id: int) -> Optional[PriceTemplate]:
    return db.scalar(select(PriceTemplate).where(PriceTemplate.supplier_id == supplier_id))


def current_list(db: Session, supplier_id: int, day: Optional[date] = None) -> Optional[PriceList]:
    """Zatwierdzony cennik obowiązujący danego dnia; przy kilku: najnowszy (od dnia startu)."""
    day = day or date.today()
    return db.scalar(
        select(PriceList).where(
            PriceList.supplier_id == supplier_id, PriceList.status == "zatwierdzony", PriceList.valid_from <= day,
            (PriceList.valid_to.is_(None)) | (PriceList.valid_to >= day),
        ).order_by(PriceList.valid_from.desc(), PriceList.id.desc()).limit(1)
    )


def previous_list(db: Session, pl: PriceList) -> Optional[PriceList]:
    return db.scalar(
        select(PriceList).where(
            PriceList.supplier_id == pl.supplier_id, PriceList.status == "zatwierdzony", PriceList.id != pl.id,
            PriceList.valid_from <= pl.valid_from,
        ).order_by(PriceList.valid_from.desc(), PriceList.id.desc()).limit(1)
    )


def latest_draft(db: Session, supplier_id: int) -> Optional[PriceList]:
    return db.scalar(select(PriceList).where(PriceList.supplier_id == supplier_id, PriceList.status == "projekt")
                     .order_by(PriceList.id.desc()).limit(1))


def changes(db: Session, tpl: PriceTemplate, new: PriceList, old: Optional[PriceList]) -> dict:
    """Co się zmieniło wobec poprzedniego cennika (do sprawdzenia przed zatwierdzeniem)."""
    nv, ov = values_of(new), values_of(old)
    secs = form_sections(tpl)
    labels = {f["key"]: f["label"] for s in secs["sections"] for r in s["rows"] for f in r["fields"]}
    labels.update({f["key"]: f["label"] for f in secs["oh"]})
    changed = [(labels.get(k, k), ov.get(k), nv.get(k)) for k in labels if ov.get(k) != nv.get(k) and (k in nv or k in ov)]
    return {"changed": changed, "count": len(nv), "same": len([k for k in nv if ov.get(k) == nv.get(k)])}


def stale(pl: Optional[PriceList], today: Optional[date] = None) -> bool:
    today = today or date.today()
    return pl is None or (pl.valid_to is not None and pl.valid_to < today) or (today - pl.valid_from).days > STALE_DAYS


# --------------------------------------------------------------------------
# Cena bazowa dla okresu umowy
# --------------------------------------------------------------------------

def months_per_year(start: date, months: int) -> dict[int, int]:
    out: dict[int, int] = {}
    y, m = start.year, start.month
    for _ in range(months):
        out[y] = out.get(y, 0) + 1
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@dataclass
class Base:
    zones: list[Decimal] = field(default_factory=list)  # średnia ważona cena bazowa w każdej strefie
    oh: Optional[Decimal] = None
    how: str = ""  # „blok 2027-2029” albo „średnia ważona: 2026 (9 mies.), 2027 (12 mies.)”
    segment: Optional[Segment] = None
    error: str = ""
    warning: str = ""


def base_for(tpl: PriceTemplate, pl: PriceList, *, product: str, group: str, volume: Decimal,
             start: date, months: int) -> Base:
    segs = parse_segments(tpl.split, tpl.segments)
    if tpl.max_volume_mwh is not None and volume > tpl.max_volume_mwh:
        return Base(error=f"wolumen ponad zakres cennika (do {tpl.max_volume_mwh.normalize():f} MWh): potrzebna wycena indywidualna")
    if tpl.split == "grupy":
        seg = next((s for s in segs if s.key.lower() == (group or "").lower()), None)
        if not seg:
            return Base(error=f"cennik nie ma grupy taryfowej {group or '(nie wybrano)'}")
    else:
        seg = next((s for i, s in enumerate(segs)
                    if (volume > s.low or (i == 0 and volume >= s.low)) and volume <= s.high), None)
        if not seg:
            return Base(error="wolumen poza przedziałami cennika: potrzebna wycena indywidualna")
    prices = {(it.period, it.zone): it.value for it in pl.items
              if it.kind == "cena" and it.product == product and it.segment == seg.key}
    per_year = months_per_year(start, months)
    first, last = min(per_year), max(per_year)
    pers = parse_periods(tpl.periods)
    result = Base(segment=seg)
    block = next((p for p in pers if p.is_block and p.first == first and p.last == last
                  and all((p.label, z) in prices for z in range(1, seg.zones + 1))), None)
    if block:
        result.zones = [prices[(block.label, z)] for z in range(1, seg.zones + 1)]
        result.how = f"blok {block.label}"
    else:
        missing = [y for y in per_year if any((str(y), z) not in prices for z in range(1, seg.zones + 1))]
        if missing:
            return Base(segment=seg, error="brak ceny na: " + ", ".join(map(str, missing))
                        + (" (i brak bloku na cały okres)" if any(p.is_block for p in pers) else ""))
        result.zones = [eng.zl(sum((prices[(str(y), z)] * n for y, n in per_year.items()), Decimal(0)) / months)
                        for z in range(1, seg.zones + 1)]
        result.how = "średnia ważona: " + ", ".join(f"{y} ({n} mies.)" for y, n in sorted(per_year.items())) \
            if len(per_year) > 1 else f"rok {first}"
    oh = next((it.value for it in pl.items if it.kind == "oh" and it.segment == seg.key), None)
    result.oh = oh
    if tpl.individual_from_mwh is not None and volume >= tpl.individual_from_mwh:
        result.warning = f"od {tpl.individual_from_mwh.normalize():f} MWh spółka robi wycenę indywidualną: może być korzystniejsza"
    return result


# --------------------------------------------------------------------------
# Kalkulator
# --------------------------------------------------------------------------

@dataclass
class Row:
    supplier: Supplier
    free: bool
    price_list: Optional[PriceList] = None
    base: Optional[Base] = None
    client_prices: list[Decimal] = field(default_factory=list)
    margins: list[Decimal] = field(default_factory=list)
    margin_avg: Decimal = Decimal(0)
    base_avg: Decimal = Decimal(0)
    limit: Optional[Decimal] = None
    over_limit: bool = False
    total_markup: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    tranche_a: Decimal = Decimal(0)
    first_tranche_pct: Optional[Decimal] = None
    oh_client: Optional[Decimal] = None
    oh_fixed: bool = True
    oh_extra_total: Decimal = Decimal(0)
    oh_commission: Decimal = Decimal(0)
    client_year_cost: Decimal = Decimal(0)
    changed_today: bool = False
    error: str = ""


def calculate(db: Session, *, owner_id: int, suppliers: list[Supplier], free_ids: set[int], product: str, group: str,
              volume: Decimal, start: date, months: int, client_prices: list[Decimal], shares: list[Decimal],
              oh_client: Optional[Decimal], points: int, today: Optional[date] = None) -> list[Row]:
    """Ta sama oferta dla klienta w kilku spółkach: marża w każdej strefie, prowizja handlowca,
    pierwsza transza, opłata handlowa i roczny koszt klienta. Kwoty handlowca, bez udziału brokera."""
    today = today or date.today()
    rate = svc.user_rate_on(db, owner_id, today)
    share = rate.trader_share_pct if rate else Decimal(0)
    rows = []
    for s in suppliers:
        r = Row(s, s.id in free_ids)
        tpl, pl = template_of(db, s.id), current_list(db, s.id, today)
        r.price_list = pl
        rs = svc.rule_set_on(db, s.id, today)
        r.limit = rs.max_markup_pln_mwh if rs else None
        r.first_tranche_pct = rs.first_tranche_pct if rs else None
        if not tpl or not pl:
            r.error = "brak zatwierdzonego cennika"
            rows.append(r)
            continue
        if product not in products_of(tpl):
            r.error = f"spółka nie ma w cenniku produktu {PRICE_PRODUCTS.get(product, product).lower()}"
            rows.append(r)
            continue
        if rs is None:
            r.error = "spółka nie ma reguł prowizji"
            rows.append(r)
            continue
        r.changed_today = pl.valid_from == today and previous_list(db, pl) is not None
        b = base_for(tpl, pl, product=product, group=group, volume=volume, start=start, months=months)
        r.base = b
        if b.error:
            r.error = b.error
            rows.append(r)
            continue
        n = len(b.zones)
        # ceny klienta i udziały stref: przy grupie jednostrefowej albo cenniku wg wolumenu — jedna strefa
        if n == 1:
            total_share = sum(shares[:len(client_prices)], Decimal(0)) or Decimal(1)
            avg_client = sum((p * w for p, w in zip(client_prices, shares)), Decimal(0)) / total_share \
                if len(client_prices) > 1 else client_prices[0]
            prices_z, shares_z = [eng.zl(avg_client)], [Decimal(1)]
        else:
            if len(client_prices) < n:
                r.error = f"podaj cenę dla klienta w każdej z {n} stref"
                rows.append(r)
                continue
            prices_z = client_prices[:n]
            total = sum(shares[:n], Decimal(0))
            shares_z = [w / total for w in shares[:n]] if total > 0 else [Decimal(1) / n] * n
        r.client_prices = prices_z
        r.margins = [eng.zl(p - bz) for p, bz in zip(prices_z, b.zones)]
        r.margin_avg = eng.zl(sum((m * w for m, w in zip(r.margins, shares_z)), Decimal(0)))
        r.base_avg = eng.zl(sum((bz * w for bz, w in zip(b.zones, shares_z)), Decimal(0)))
        if any(m < 0 for m in r.margins):
            r.error = "cena dla klienta niższa niż cena bazowa w co najmniej jednej strefie"
            rows.append(r)
            continue
        r.over_limit = r.limit is not None and any(m > r.limit for m in r.margins)
        bd = eng.calculate(eng.ContractTerms(
            annual_volume_mwh=volume, term_months=months, markup_pln_mwh=r.margin_avg,
            broker_share_pct=eng.D(rs.broker_share_pct), first_tranche_pct=eng.D(rs.first_tranche_pct),
            trader_share_pct=eng.D(share),
        ))
        r.total_markup, r.commission, r.tranche_a = bd.total_markup, bd.trader.total, bd.trader.tranche1
        base_oh = b.oh or Decimal(0)
        r.oh_fixed = tpl.oh_mode == "stala"
        if r.oh_fixed or oh_client is None:
            r.oh_client = base_oh
        else:
            r.oh_client = max(oh_client, base_oh)
            r.oh_extra_total = eng.zl((r.oh_client - base_oh) * months * points)
            # prowizja od dopłaty do OH w tym samym procencie co od sprzedaży (ustalenie 10.11.2026)
            r.oh_commission = eng.zl(r.oh_extra_total * share / 100)
            r.commission += r.oh_commission
        avg_price = sum((p * w for p, w in zip(prices_z, shares_z)), Decimal(0))
        r.client_year_cost = eng.zl(volume * avg_price + r.oh_client * 12 * points)
        rows.append(r)
    rows.sort(key=lambda x: (bool(x.error), x.over_limit, -x.commission))
    return rows
