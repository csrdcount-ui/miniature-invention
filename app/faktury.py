"""Dane z faktur: punkty poboru, wolumen roczny, profil zużycia, zadania „odeślij do BOK”.

Bez FastAPI (jak engine i pipeline). Metoda liczenia wolumenu od właścicielki (13.11.2026):
- najlepiej 6 faktur: suma zużycia z okresów obejmujących co najmniej 10 miesięcy,
  przeliczona na rok; sześć faktur pokazuje też, czy profil jest płaski czy sezonowy;
- albo dwie faktury oddalone o co najmniej 10 miesięcy: różnica stanów licznika
  (na każdej fakturze jest stan licznika), przeliczona na rok.

Zdjęcia faktur: BOK je pobiera do dokumentacji biura i usuwa z platformy dopiero po potwierdzeniu
(zasada właścicielki 13.11.2026), patrz finish_task, mark_downloaded, archive_photos.

Miejsce na płatną opcję rozpoznawania faktur przez AI: `extractor()` zwraca dziś None.
Gdy biuro ją wykupi (umowa powierzenia danych, koszt jednej faktury w abonamencie),
rozpoznane dane trafią jako InvoiceReading z source="ai" i verified=False, a BOK je zatwierdzi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from statistics import mean, pstdev
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ROLE_BOK,
    TARIFF_GROUPS,
    Client,
    InvoicePhoto,
    InvoiceReading,
    InvoiceTask,
    MeteringPoint,
    User,
)
from .pipeline import add_event, can_sell_for, can_view_client
from .services import BusinessError

MIN_SPAN_DAYS = 300          # „co najmniej 10 miesięcy”
PROFILE_MIN_PERIODS = 4      # mniej faktur nie mówi nic o sezonowości
SEASONAL_CV = Decimal("0.25")  # zmienność dziennego zużycia między okresami powyżej 25% = sezonowy (do potwierdzenia)
METHODS_DIFF_WARN = Decimal("0.10")
MAX_PHOTOS = 8
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
PHOTO_MAX_SIDE = 2000
TASK_RECENT_DAYS = 7


# --------------------------------------------------------------------------
# Wolumen roczny i profil
# --------------------------------------------------------------------------

@dataclass
class Volume:
    mwh: Optional[Decimal] = None
    method: str = ""
    days: int = 0
    warning: str = ""
    error: str = ""


def _days_set(readings: list[InvoiceReading]) -> tuple[set[int], bool]:
    days: set[int] = set()
    overlap = False
    for r in readings:
        rng = set(range(r.period_from.toordinal(), r.period_to.toordinal() + 1))
        if days & rng and len(days & rng) > 1:  # wspólny jeden dzień na styku okresów to norma
            overlap = True
        days |= rng
    return days, overlap


def volume_from_consumption(readings: list[InvoiceReading]) -> Volume:
    rs = [r for r in readings if r.consumption_kwh is not None and r.period_to > r.period_from]
    if not rs:
        return Volume(error="brak zużycia z faktur")
    days, overlap = _days_set(rs)
    covered = len(days)
    total = sum((Decimal(r.consumption_kwh) for r in rs), Decimal(0))
    if covered < MIN_SPAN_DAYS:
        return Volume(days=covered, error=f"faktury obejmują {covered} dni, potrzeba co najmniej {MIN_SPAN_DAYS}")
    mwh = (total * 365 / covered / 1000).quantize(Decimal("0.001"))
    return Volume(mwh=mwh, method=f"suma zużycia z {len(rs)} faktur, {covered} dni, przeliczona na rok", days=covered,
                  warning="okresy faktur nakładają się: sprawdź, czy któraś faktura nie jest wpisana dwa razy" if overlap else "")


def volume_from_meter(readings: list[InvoiceReading]) -> Volume:
    pts: list[tuple[date, Decimal]] = []
    for r in readings:
        if r.meter_start is not None:
            pts.append((r.period_from, Decimal(r.meter_start)))
        if r.meter_end is not None:
            pts.append((r.period_to, Decimal(r.meter_end)))
    if len(pts) < 2:
        return Volume(error="brak dwóch stanów licznika")
    first, last = min(pts), max(pts)
    span = (last[0] - first[0]).days
    if span < MIN_SPAN_DAYS:
        return Volume(days=span, error=f"stany licznika dzieli {span} dni, potrzeba co najmniej {MIN_SPAN_DAYS}")
    diff = last[1] - first[1]
    if diff < 0:
        return Volume(days=span, error="późniejszy stan licznika jest mniejszy: wymiana licznika albo pomyłka we wpisie")
    mwh = (diff * 365 / span / 1000).quantize(Decimal("0.001"))
    return Volume(mwh=mwh, method=f"różnica stanów licznika z {first[0]:%d.%m.%Y} i {last[0]:%d.%m.%Y} ({span} dni), przeliczona na rok",
                  days=span)


def annual_volume(readings: list[InvoiceReading]) -> Volume:
    """Najpierw suma zużycia (więcej faktur, dokładniej), potem różnica stanów licznika."""
    a, b = volume_from_consumption(readings), volume_from_meter(readings)
    best = a if a.mwh is not None else b
    if best.mwh is None:
        if "wymiana licznika" in b.error:
            return Volume(days=b.days, error=b.error[0].upper() + b.error[1:] + ".")
        return Volume(error="Za mało danych do wolumenu rocznego: potrzeba faktur z co najmniej 10 miesięcy "
                            "albo dwóch stanów licznika oddalonych o co najmniej 10 miesięcy.")
    if a.mwh is not None and b.mwh is not None and b.mwh > 0:
        if abs(a.mwh - b.mwh) / b.mwh > METHODS_DIFF_WARN:
            extra = f"suma zużycia daje {a.mwh} MWh, a stany licznika {b.mwh} MWh: sprawdź wpisane liczby"
            best.warning = f"{best.warning}; {extra}" if best.warning else extra
    return best


@dataclass
class Profile:
    kind: str = ""     # „płaski”, „sezonowy” albo pusty, gdy za mało danych
    text: str = ""


def usage_profile(readings: list[InvoiceReading]) -> Profile:
    rs = [r for r in readings if r.consumption_kwh is not None and r.period_to > r.period_from]
    if len(rs) < PROFILE_MIN_PERIODS:
        return Profile(text=f"Profil oceniam od {PROFILE_MIN_PERIODS} faktur (najlepiej 6); jest {len(rs)}.")
    daily = [(r, Decimal(r.consumption_kwh) / ((r.period_to - r.period_from).days + 1)) for r in rs]
    vals = [float(d) for _, d in daily]
    avg = mean(vals)
    if avg <= 0:
        return Profile(text="Zużycie zerowe: profilu nie da się ocenić.")
    cv = Decimal(str(pstdev(vals) / avg))
    hi = max(daily, key=lambda x: x[1])[0]
    lo = min(daily, key=lambda x: x[1])[0]
    span = f"najwięcej w okresie {hi.period_from:%m.%Y}–{hi.period_to:%m.%Y}, najmniej w {lo.period_from:%m.%Y}–{lo.period_to:%m.%Y}"
    if cv > SEASONAL_CV:
        return Profile("sezonowy", f"Profil sezonowy: zużycie dzienne różni się między okresami o {int(cv * 100)}%; {span}.")
    return Profile("płaski", f"Profil płaski: zużycie dzienne podobne w każdym okresie (różnice {int(cv * 100)}%).")


def notice_deadline(p: MeteringPoint) -> Optional[date]:
    """Ostatni dzień na wypowiedzenie obecnej umowy: koniec umowy minus okres wypowiedzenia."""
    if not p.contract_end or p.notice_months is None:
        return None
    y, m = divmod(p.contract_end.month - 1 - p.notice_months, 12)
    year, month = p.contract_end.year + y, m + 1
    import calendar
    return date(year, month, min(p.contract_end.day, calendar.monthrange(year, month)[1]))


@dataclass
class PointSummary:
    point: MeteringPoint
    volume: Volume
    profile: Profile


def summarize(c: Client) -> tuple[list[PointSummary], Optional[Decimal], str]:
    """Punkty klienta z wolumenem i profilem, suma wolumenu i grupa taryfowa do kalkulatora."""
    rows = [PointSummary(p, annual_volume(p.readings), usage_profile(p.readings)) for p in c.points]
    vols = [r.volume.mwh for r in rows if r.volume.mwh is not None]
    total = sum(vols, Decimal(0)) if vols and len(vols) == len(rows) else None
    group = next((p.tariff_group for p in c.points if p.tariff_group), "")
    return rows, total, group


# --------------------------------------------------------------------------
# Wpisywanie danych (handlowiec, jego menedżer, właściciel, BOK)
# --------------------------------------------------------------------------

def can_enter_data(user: User, c: Client) -> bool:
    return can_sell_for(user, c) or (user.role == ROLE_BOK and can_view_client(user, c))


def add_point(db: Session, c: Client, user: User, *, ppe: str, address: str, tariff_group: str, current_seller: str,
              contract_end: Optional[date], notice_months: Optional[int]) -> MeteringPoint:
    if not (ppe or address):
        raise BusinessError("Podaj numer punktu poboru albo adres.")
    p = MeteringPoint(client=c, ppe=ppe[:50], address=address[:300], tariff_group=tariff_group if tariff_group in TARIFF_GROUPS else "",
                      current_seller=current_seller[:120], contract_end=contract_end, notice_months=notice_months,
                      created_by_id=user.id)
    db.add(p)
    add_event(db, c, user, "notatka", f"Dodano punkt poboru {ppe or address}.")
    return p


def add_reading(db: Session, p: MeteringPoint, user: User, *, period_from: date, period_to: date,
                meter_start: Optional[Decimal], meter_end: Optional[Decimal], consumption_kwh: Optional[Decimal]) -> InvoiceReading:
    if period_to <= period_from:
        raise BusinessError("Koniec okresu rozliczeniowego musi być po jego początku.")
    if (period_to - period_from).days > 400:
        raise BusinessError("Okres rozliczeniowy dłuższy niż rok: sprawdź daty.")
    if consumption_kwh is None and meter_end is None:
        raise BusinessError("Wpisz zużycie z faktury albo stan licznika na koniec okresu.")
    if meter_start is not None and meter_end is not None and meter_end < meter_start:
        raise BusinessError("Stan licznika na koniec okresu jest mniejszy niż na początku: sprawdź liczby.")
    r = InvoiceReading(point=p, period_from=period_from, period_to=period_to, meter_start=meter_start, meter_end=meter_end,
                       consumption_kwh=consumption_kwh, source="bok" if user.role == ROLE_BOK else "handlowiec",
                       entered_by_id=user.id)
    db.add(r)
    add_event(db, p.client, user, "notatka", f"Dane z faktury za {period_from:%d.%m.%Y}–{period_to:%d.%m.%Y}, punkt {p.ppe or p.address}.")
    return r


# --------------------------------------------------------------------------
# Zdjęcia faktur i zadania dla BOK
# --------------------------------------------------------------------------

def prepare_photo(raw: bytes) -> tuple[bytes, str]:
    """Pomniejsza zdjęcie do JPEG (krótszy bok czytelny, plik kilkaset KB). PDF zostaje bez zmian."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise BusinessError(f"Plik jest za duży: najwyżej {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if raw[:5] == b"%PDF-":
        return raw, "application/pdf"
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # zdjęcia z telefonu bywają obrócone w metadanych
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise BusinessError("To nie jest zdjęcie ani PDF. Zrób zdjęcie faktury aparatem albo wybierz plik.")
    img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
    out = BytesIO()
    img.save(out, "JPEG", quality=80, optimize=True)
    return out.getvalue(), "image/jpeg"


def request_task(db: Session, c: Client, user: User, files: list[bytes], note: str) -> InvoiceTask:
    if not can_sell_for(user, c):
        raise BusinessError("Nie możesz przekazać faktur tego klienta.")
    if not files:
        raise BusinessError("Dołącz co najmniej jedno zdjęcie faktury.")
    if len(files) > MAX_PHOTOS:
        raise BusinessError(f"Najwyżej {MAX_PHOTOS} zdjęć w jednym przekazaniu.")
    t = InvoiceTask(client=c, note=note.strip()[:1000], requested_by_id=user.id)
    for raw in files:
        data, ctype = prepare_photo(raw)
        t.photos.append(InvoicePhoto(data=data, content_type=ctype))
    db.add(t)
    add_event(db, c, user, "bok", f"Przekazano do BOK {len(files)} {'zdjęcie' if len(files) == 1 else 'zdjęcia' if len(files) < 5 else 'zdjęć'} faktur do wprowadzenia.")
    return t


def finish_task(db: Session, t: InvoiceTask, user: User, note: str, *, cancel: bool = False) -> None:
    """BOK kończy zadanie (dane wpisane albo nieczytelne). Zdjęcia ZOSTAJĄ: BOK pobiera je do
    dokumentacji biura dla spółki obrotu i dopiero potem, po potwierdzeniu, usuwa (archive_photos)."""
    if t.status != "czeka":
        raise BusinessError("To zadanie jest już zamknięte.")
    t.status = "anulowane" if cancel else "zrobione"
    t.done_by_id, t.done_at, t.done_note = user.id, datetime.utcnow(), note.strip()[:1000]
    add_event(db, t.client, user, "bok", ("BOK anulował zadanie z fakturami" if cancel else "BOK wprowadził dane z faktur")
              + (f": {t.done_note}" if t.done_note else "."))


def mark_downloaded(photos: list[InvoicePhoto], user: User) -> None:
    now = datetime.utcnow()
    for ph in photos:
        ph.downloaded_at, ph.downloaded_by_id = now, user.id


def all_downloaded(t: InvoiceTask) -> bool:
    return bool(t.photos) and all(ph.downloaded_at for ph in t.photos)


def archive_photos(db: Session, t: InvoiceTask, user: User, *, confirmed: bool, without_download: bool = False) -> int:
    """Usuwa zdjęcia z platformy dopiero po potwierdzeniu, że są w dokumentacji biura.
    Niepobrane pliki wymagają osobnego potwierdzenia, że nie są potrzebne."""
    if t.status == "czeka":
        raise BusinessError("Najpierw wpisz dane i zamknij zadanie, potem zarchiwizuj zdjęcia.")
    if not t.photos:
        raise BusinessError("W tym zadaniu nie ma już zdjęć.")
    if not confirmed:
        raise BusinessError("Zaznacz potwierdzenie, że pliki są zapisane w dokumentacji biura.")
    if not all_downloaded(t) and not without_download:
        raise BusinessError("Nie wszystkie pliki zostały pobrane. Pobierz je albo potwierdź, że nie są potrzebne.")
    n = len(t.photos)
    t.photos.clear()  # delete-orphan: pliki znikają z bazy przy zapisie
    t.archived_at, t.archived_by_id = datetime.utcnow(), user.id
    add_event(db, t.client, user, "bok", f"BOK zarchiwizował faktury ({n}) w dokumentacji biura i usunął je z platformy.")
    return n


def _slug(text: str) -> str:
    import unicodedata
    text = text.translate(str.maketrans("łŁ", "lL"))  # „ł” nie rozkłada się w NFKD i by znikało
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch if ch.isalnum() else "-" for ch in ascii_).strip("-")[:60] or "klient"


def photo_filename(t: InvoiceTask, ph: InvoicePhoto, index: int) -> str:
    """Nazwa pliku do dokumentacji: klient, NIP, data przesłania, numer strony."""
    ext = "pdf" if ph.content_type == "application/pdf" else "jpg"
    nip = f"_NIP{t.client.nip}" if t.client.nip else ""
    return f"{_slug(t.client.name)}{nip}_faktury_{t.requested_at:%Y-%m-%d}_{index}.{ext}"


def zip_name(t: InvoiceTask) -> str:
    nip = f"_NIP{t.client.nip}" if t.client.nip else ""
    return f"{_slug(t.client.name)}{nip}_faktury_{t.requested_at:%Y-%m-%d}.zip"


def zip_task(t: InvoiceTask) -> bytes:
    import zipfile
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:  # JPEG i PDF są już skompresowane
        for i, ph in enumerate(t.photos, 1):
            z.writestr(photo_filename(t, ph, i), ph.data)
    return out.getvalue()


def to_archive(db: Session) -> list[InvoiceTask]:
    """Zamknięte zadania, w których zdjęcia czekają na pobranie i archiwizację przez BOK."""
    return [t for t in db.scalars(select(InvoiceTask).where(InvoiceTask.status != "czeka", InvoiceTask.archived_at.is_(None))
                                  .order_by(InvoiceTask.done_at)) if t.photos]


def pending_tasks(db: Session) -> list[InvoiceTask]:
    return list(db.scalars(select(InvoiceTask).where(InvoiceTask.status == "czeka").order_by(InvoiceTask.requested_at)))


def recent_done_for(db: Session, user: User) -> list[InvoiceTask]:
    since = datetime.utcnow() - timedelta(days=TASK_RECENT_DAYS)
    return list(db.scalars(
        select(InvoiceTask).join(Client).where(Client.owner_id == user.id, InvoiceTask.status != "czeka",
                                               InvoiceTask.done_at >= since).order_by(InvoiceTask.done_at.desc())
    ))


# --------------------------------------------------------------------------
# Miejsce na płatną opcję: rozpoznawanie faktur przez AI (wyłączone)
# --------------------------------------------------------------------------

class InvoiceExtractor(Protocol):
    """Rozpoznaje dane z faktury. Wynik zapisujemy jako InvoiceReading(source="ai", verified=False)."""

    def extract(self, photos: list[InvoicePhoto]) -> list[dict]: ...


def extractor() -> Optional[InvoiceExtractor]:
    """Dziś zawsze None: rozpoznawanie przez AI to przyszła opcja premium (umowa powierzenia, koszt)."""
    return None
