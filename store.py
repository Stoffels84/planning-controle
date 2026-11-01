"""Datalaag voor de v0.2-proefversie (PostgreSQL of lokale SQLite-test).

Geen echte personeelsgegevens gebruiken op gratis Community Cloud zonder goedkeuring.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
import hashlib
import hmac
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.exc import IntegrityError

from demo_data import build_demo
from months_v012 import period_key, shared_fields, merge_shared, new_month_payload
from month_copy_v013 import copy_month_demand_rows
from requests_v010 import leave_days, absence_credit
from swap_v011 import make_swap_plan, verify_swap_with_solver


class SetupError(RuntimeError):
    pass


class ConflictError(RuntimeError):
    pass


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    employee_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspace"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MonthWorkspace(Base):
    """Afzonderlijke conceptinvoer per kalendermaand; index = YYYYMM."""
    __tablename__ = "month_workspaces"
    period: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SharedCatalog(Base):
    """Eén catalogus van controleurs, dienstnummers, regels en taaktypes."""
    __tablename__ = "shared_catalog"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class PlanningVersion(Base):
    __tablename__ = "planning_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class UsedRecoveryKey(Base):
    """Eenmalige herstelcodes: alleen een SHA-256-vingerafdruk, nooit de code zelf."""
    __tablename__ = "used_recovery_keys"
    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    admin_id: Mapped[str] = mapped_column(String(64), nullable=False)


class LeaveRequest(Base):
    """Persistente aanvraag, los van de JSON-werkruimte (geen sessie-conflict)."""
    __tablename__ = "leave_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(64))
    hours_per_day: Mapped[float | None] = mapped_column(nullable=True)


class LeaveCancellation(Base):
    """Intrekkingsverzoek voor reeds goedgekeurd verlof; behoudt de beslissingshistoriek."""
    __tablename__ = "leave_cancellations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_request_id: Mapped[int] = mapped_column(Integer, ForeignKey("leave_requests.id"), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(400), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(64))


class LeaveCancellationSelection(Base):
    """v0.20: selectie van dagen per intrekkingsverzoek; nieuwe tabel, geen wijziging van oude tabellen.

    Voor oude v0.18.1-verzoeken zonder selectie betekent het verzoek 'alle resterende dagen'.
    """
    __tablename__ = "leave_cancellation_selections"
    cancellation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leave_cancellations.id"), primary_key=True)
    days: Mapped[list] = mapped_column(JSON, nullable=False)


class SwapRequest(Base):
    """Een ruilvoorstel gekoppeld aan exact één gepubliceerde planversie."""
    __tablename__ = "swap_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("planning_versions.id"), nullable=False)
    initiator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    colleague_id: Mapped[str] = mapped_column(String(64), nullable=False)
    own_day: Mapped[date] = mapped_column(Date, nullable=False)
    own_shift: Mapped[str] = mapped_column(String(80), nullable=False)
    their_day: Mapped[date] = mapped_column(Date, nullable=False)
    their_shift: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(64))
    new_plan_id: Mapped[int | None] = mapped_column(Integer)


class InboxNotice(Base):
    """Melding per account, niet gedeeld via een werkruimte of sessiestatus."""
    __tablename__ = "inbox_notices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[str] = mapped_column(String(64), ForeignKey("accounts.employee_id"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
# Dezelfde hoeveelheid argon2-werk bij een niet bestaand account.
DUMMY_HASH = HASHER.hash("dit-is-geen-geldig-gebruikerswachtwoord")
ROLES = ("admin", "planner", "controleur")


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_engine(database_url: str):
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
    if not database_url.startswith(("postgresql+psycopg://", "sqlite+pysqlite://")):
        raise SetupError("Gebruik PostgreSQL met psycopg (of SQLite uitsluitend lokaal voor tests).")
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=1800)


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def check_password_strength(password: str):
    if len(password) < 14 or len(password) > 128:
        raise ValueError("Gebruik een wachtwoord van 14 tot 128 tekens.")


def _audit(s, actor: str, action: str) -> None:
    s.add(AuditEvent(actor=actor, action=action, created_at=now()))


def _notice(s, recipient: str, event_key: str, title: str, body: str) -> None:
    """Transactieve inboxmelding. De afzender kiest de ontvanger server-side."""
    who = s.get(Account, recipient)
    if not who or not who.active:
        return
    s.add(InboxNotice(recipient_id=recipient, event_key=event_key,
                      title=title[:160], body=body[:500], created_at=now()))


def _notify_managers(s, key: str, title: str, body: str) -> None:
    managers = s.scalars(select(Account).where(
        Account.active.is_(True), Account.role.in_(("admin", "planner")))).all()
    for manager in managers:
        _notice(s, manager.employee_id, f"{key}:{manager.employee_id}", title, body)


def notifications_for(engine, actor: str, limit: int = 80) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("Ongeldige meldingenlimiet.")
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        rows = s.scalars(select(InboxNotice).where(InboxNotice.recipient_id == actor)
                         .order_by(InboxNotice.id.desc()).limit(limit)).all()
        return [{"id": row.id, "title": row.title, "body": row.body,
                 "created_at": row.created_at.isoformat(),
                 "read": row.read_at is not None} for row in rows]


def mark_notice_read(engine, notice_id: int, actor: str) -> None:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        row = s.scalar(select(InboxNotice).where(InboxNotice.id == notice_id).with_for_update())
        if not row or row.recipient_id != actor:
            raise ValueError("Melding niet beschikbaar.")
        if row.read_at is None:
            row.read_at = now()


def mark_all_notices_read(engine, actor: str) -> None:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        rows = s.scalars(select(InboxNotice).where(
            InboxNotice.recipient_id == actor, InboxNotice.read_at.is_(None))).all()
        moment = now()
        for row in rows:
            row.read_at = moment


def _publish_notifications(s, row: PlanningVersion, earlier: PlanningVersion | None) -> None:
    """Eerste publicatie: alle actieve controleurs. Herpublicatie: enkel gewijzigde roosters.

    De vergelijking gebruikt uitsluitend eigen toewijzingen. Geen vertrouwelijke
    gegevens van collega's worden in de melding opgenomen.
    """
    from portal_v017 import personal_publication_changes
    previous = earlier.payload.get("assignments", []) if earlier and isinstance(earlier.payload, dict) else []
    current = row.payload.get("assignments", []) if isinstance(row.payload, dict) else []
    recipients = s.scalars(select(Account).where(
        Account.active.is_(True), Account.role == "controleur")).all()
    for recipient in recipients:
        eid = recipient.employee_id
        if earlier:
            changed = personal_publication_changes(previous, current, eid)
            if not changed:
                continue
            title = f"Wijziging maandplanning {row.month:02d}/{row.year}"
            body = (f"Je gepubliceerde planning is gewijzigd op {len(changed)} "
                    f"dag(en). Open Mijn planning voor de details.")
        else:
            title = f"Maandplanning {row.month:02d}/{row.year} gepubliceerd"
            body = "Je maandplanning is gepubliceerd. Bekijk je eigen diensten bij Mijn planning."
        _notice(s, eid, f"publish:{row.id}:{eid}", title, body)

def initialize(engine, bootstrap_id: str = "", bootstrap_password: str = "") -> None:
    Base.metadata.create_all(engine)
    Session = session_factory(engine)
    with Session.begin() as s:
        if s.get(Workspace, 1) is None:
            s.add(Workspace(id=1, payload=build_demo(), revision=1))
        if s.scalar(select(Account.employee_id).limit(1)) is None:
            if not bootstrap_id.strip() or not bootstrap_password:
                raise SetupError("Nog geen beheerder. Configureer BOOTSTRAP_ADMIN_ID en BOOTSTRAP_ADMIN_PASSWORD via Streamlit Secrets.")
            check_password_strength(bootstrap_password)
            s.add(Account(employee_id=bootstrap_id.strip(), name="Hoofdbeheerder (test)",
                          password_hash=HASHER.hash(bootstrap_password), role="admin", active=True,
                          must_change_password=True, failed_logins=0))
            _audit(s, bootstrap_id.strip(), "Eerste beheerder aangemaakt")


def public_account(a: Account) -> dict:
    return {"employee_id": a.employee_id, "name": a.name, "role": a.role,
            "active": a.active, "must_change_password": a.must_change_password,
            # Interne sessie-invalidering bij wachtwoordverandering.
            "auth_hash": a.password_hash}


def lookup_account(engine, employee_id: str) -> dict | None:
    with session_factory(engine)() as s:
        a = s.get(Account, employee_id)
        return public_account(a) if a is not None else None


def authenticate(engine, employee_id: str, password: str) -> dict | None:
    """Uniforme foutuitkomst; vergrendelt account na vijf mislukte pogingen."""
    with session_factory(engine).begin() as s:
        a = s.scalar(select(Account).where(Account.employee_id == employee_id).with_for_update())
        try:
            valid = HASHER.verify(a.password_hash if a else DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError, ValueError):
            valid = False
        if not a or not a.active:
            return None
        if a.locked_until and a.locked_until.replace(tzinfo=timezone.utc) > now():
            return None
        if not valid:
            a.failed_logins = (a.failed_logins or 0) + 1
            if a.failed_logins >= 5:
                a.locked_until = now() + timedelta(minutes=15)
                a.failed_logins = 0
            return None
        a.failed_logins = 0
        a.locked_until = None
        return public_account(a)


def initialize_months(engine) -> None:
    """Niet-destructieve migratie van de v0.11-werkruimte, telkens idempotent.

    De oude Workspace-tabel wordt bewust NIET verwijderd/gewijzigd en vormt
    een herstelpunt. Gepubliceerde planningen blijven onaangetast.
    """
    with session_factory(engine).begin() as s:
        legacy = s.get(Workspace, 1)
        if legacy is None:
            raise SetupError("De bestaande werkruimte ontbreekt.")
        shared = s.get(SharedCatalog, 1)
        if shared is None:
            s.add(SharedCatalog(id=1, payload=shared_fields(legacy.payload)))
        period = period_key(int(legacy.payload["year"]), int(legacy.payload["month"]))
        if s.get(MonthWorkspace, period) is None:
            s.add(MonthWorkspace(period=period, payload=legacy.payload, revision=legacy.revision))


def list_month_workspaces(engine) -> list[dict]:
    """De bestaande maanden tonen, met afzonderlijke concept- en publicatiestatus."""
    initialize_months(engine)
    with session_factory(engine)() as s:
        rows = s.scalars(select(MonthWorkspace).order_by(MonthWorkspace.period)).all()
        summaries = []
        for w in rows:
            year, month = divmod(w.period, 100)
            published = s.scalar(select(PlanningVersion.id).where(
                PlanningVersion.year == year, PlanningVersion.month == month,
                PlanningVersion.published_at.is_not(None)).order_by(
                    PlanningVersion.published_at.desc(), PlanningVersion.id.desc()).limit(1))
            summaries.append({"year": year, "month": month, "revision": w.revision,
                              "published": bool(published),
                              "has_demand": bool(w.payload.get("demand", []))})
        return summaries



def dashboard_month_snapshots(engine, actor: str) -> list[dict]:
    """Read-only manager report; no raw personnel profiles returned.

    Latest saved plan and latest published plan may differ. The frontend can
    therefore warn about newer inputs without silently replacing publications.
    """
    initialize_months(engine)
    with session_factory(engine)() as s:
        account = s.get(Account, actor)
        if not account or not account.active or account.role not in ("admin", "planner"):
            raise ValueError("Alleen beheerders en planners mogen het dashboard bekijken.")
        months = s.scalars(select(MonthWorkspace).order_by(MonthWorkspace.period)).all()
        versions = s.scalars(select(PlanningVersion).order_by(PlanningVersion.id.desc())).all()
        by_period = {}
        for p in versions:
            key = p.year * 100 + p.month
            entry = by_period.setdefault(key, {"latest_plan": None, "published_plan": None})
            if entry["latest_plan"] is None:
                entry["latest_plan"] = p
            pub = entry["published_plan"]
            if p.published_at is not None:
                # Timestampwaarden uit oude bestanden kunnen qua tzinfo
                # verschillen. Vergelijk UTC-tijdstempels i.p.v. datetime-objecten.
                from datetime import timezone
                def published_order(v):
                    date_value = v.published_at
                    if date_value.tzinfo is None:
                        date_value = date_value.replace(tzinfo=timezone.utc)
                    return (date_value.timestamp(), v.id)
                if pub is None or published_order(p) > published_order(pub):
                    entry["published_plan"] = p
        output = []
        for m in months:
            year, month = divmod(m.period, 100)
            versions_for_month = by_period.get(m.period, {})
            def small_plan(p):
                if p is None:
                    return None
                # Historische planpayloads kunnen een onvolledig of anders
                # gevormd summary-object bevatten. Laat dat het dashboard
                # niet volledig laten crashen.
                raw_payload = p.payload if isinstance(p.payload, dict) else {}
                summary = raw_payload.get("summary", {})
                return {"id": p.id, "revision": p.workspace_revision,
                        "payload": {"summary": summary if isinstance(summary, dict) else {}}}
            raw = m.payload if isinstance(m.payload, dict) else {}
            output.append({
                "year": year, "month": month, "revision": m.revision,
                "workspace": {k: raw.get(k) if isinstance(raw.get(k), list) else []
                              for k in ("demand", "task_needs", "preferences")},
                "latest_plan": small_plan(versions_for_month.get("latest_plan")),
                "published_plan": small_plan(versions_for_month.get("published_plan")),
            })
        return output


def create_month_workspace(engine, year: int, month: int, actor: str,
                           source_period: tuple[int, int] | None = None,
                           copy_mode: str = "weekday") -> None:
    """Nieuwe maand, eventueel met alleen de behoefte uit een bestaande maand.

    De volledige creatie gebeurt in één transactie; bij ongeldige diensten of
    datums wordt noch de nieuwe maand noch de bron gewijzigd.
    """
    period = period_key(year, month)
    initialize_months(engine)
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Alleen beheerders en planners mogen maanden aanmaken.")
        shared = s.scalar(select(SharedCatalog).where(SharedCatalog.id == 1).with_for_update())
        if s.get(MonthWorkspace, period):
            raise ValueError("Deze maand bestaat al. Selecteer ze in het overzicht.")
        legacy = s.get(Workspace, 1)
        template = merge_shared(legacy.payload, shared.payload)
        state = new_month_payload(year, month, template)
        if source_period is not None:
            if len(source_period) != 2:
                raise ValueError("Ongeldige bronmaand.")
            src = s.get(MonthWorkspace, period_key(*source_period))
            if src is None:
                raise ValueError("De bronmaand bestaat niet.")
            state["demand"] = copy_month_demand_rows(
                src.payload, year, month, shared.payload.get("shifts", []), copy_mode
            )
        s.add(MonthWorkspace(period=period, payload=state, revision=1))
        _audit(s, actor, f"Nieuwe maand {year}-{month:02d} aangemaakt" +
               (f"; behoefte gekopieerd van {source_period[0]}-{source_period[1]:02d} ({copy_mode})"
                if source_period else ""))


def copy_month_workspace_demand(engine, source_year: int, source_month: int,
                                target_year: int, target_month: int,
                                expected_revision: int, actor: str,
                                mode: str = "weekday") -> int:
    """Vul een reeds aangemaakte, LEEG gebleven doelmaand vanuit een bronmaand.

    Wijzigingen zijn atomair, met revision lock; nooit automatisch bestaande
    maandbehoefte of een reeds gepubliceerde planning overschrijven.
    """
    source_key, target_key = period_key(source_year, source_month), period_key(target_year, target_month)
    initialize_months(engine)
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Alleen beheerders en planners kunnen maandbehoeften kopiëren.")
        shared = s.scalar(select(SharedCatalog).where(SharedCatalog.id == 1).with_for_update())
        source = s.get(MonthWorkspace, source_key)
        target = s.scalar(select(MonthWorkspace).where(MonthWorkspace.period == target_key).with_for_update())
        if source is None or target is None:
            raise ValueError("Bron- of doelmaand bestaat niet.")
        if target.revision != expected_revision:
            raise ConflictError("De doelmaand is ondertussen veranderd. Vernieuw eerst de pagina.")
        if target.payload.get("demand"):
            raise ValueError("Deze maand heeft al dienstbehoefte. Kopiëren is alleen toegestaan naar een lege maand.")
        publication = s.scalar(select(PlanningVersion.id).where(
            PlanningVersion.year == target_year, PlanningVersion.month == target_month,
            PlanningVersion.published_at.is_not(None)).limit(1))
        if publication is not None:
            raise ValueError("Voor deze maand is al een planning gepubliceerd. Kopiëren is geblokkeerd.")
        if shared is None:
            raise SetupError("Gedeelde dienstcatalogus ontbreekt.")
        demand = copy_month_demand_rows(source.payload, target_year, target_month,
                                        shared.payload.get("shifts", []), mode)
        if not demand:
            raise ValueError("Deze kopie zou leeg zijn. Kies een andere bronmaand of methode.")
        state = dict(target.payload)
        state["demand"] = demand
        target.payload = state
        target.revision += 1
        _audit(s, actor, f"Maandbehoefte gekopieerd {source_year}-{source_month:02d} naar "
               f"{target_year}-{target_month:02d} ({mode})")
        return target.revision


def load_month_workspace(engine, year: int, month: int) -> tuple[dict, int]:
    initialize_months(engine)
    with session_factory(engine)() as s:
        row = s.get(MonthWorkspace, period_key(year, month))
        if row is None:
            raise ValueError("Deze maand bestaat nog niet. Maak ze eerst aan.")
        shared = s.get(SharedCatalog, 1)
        return merge_shared(row.payload, shared.payload), row.revision


def _remaining_approved_leave_days(s, leave: LeaveRequest) -> list[date]:
    """Datumset die nog goedgekeurd/geblokkeerd is, na eerdere deelintrekkingen.

    Oude intrekkingen zonder selectierij zijn volledig; bij status 'cancelled'
    zijn er daarom altijd nul resterende dagen.
    """
    if leave.status != "approved":
        return []
    original = leave_days(leave.start_date, leave.end_date,
                          leave.start_date.year, leave.start_date.month)
    approved_cancels = s.scalars(select(LeaveCancellation).where(
        LeaveCancellation.leave_request_id == leave.id,
        LeaveCancellation.status == "approved")).all()
    removed: set[str] = set()
    for cancellation in approved_cancels:
        selection = s.get(LeaveCancellationSelection, cancellation.id)
        if selection is None:
            # Historische v0.18.1-volledige intrekkingen horen bij
            # leave.status == 'cancelled'; 'approved' duidt op inconsistente data.
            raise ValueError("De bestaande verlofintrekkingshistoriek is inconsistent.")
        removed.update(selection.days)
    return [d for d in original if d.isoformat() not in removed]


def _validate_leave_cancel_days(leave: LeaveRequest, remaining: list[date],
                                days: list[date] | None) -> list[date]:
    """Server-side selectie: exact, uniek, binnen goedgekeurde resterende dagen."""
    if not remaining:
        raise ValueError("Er zijn geen goedgekeurde verlofdagen meer om in te trekken.")
    if days is None:
        return list(remaining)
    if not isinstance(days, (list, tuple)) or not days:
        raise ValueError("Selecteer minstens één verlofdag om in te trekken.")
    if any(type(d) is not date for d in days):
        raise ValueError("De geselecteerde verlofdatums zijn ongeldig.")
    if len(set(days)) != len(days):
        raise ValueError("Eenzelfde verlofdag mag maar één keer worden geselecteerd.")
    if not set(days).issubset(set(remaining)):
        raise ValueError("De gekozen datum valt niet binnen het nog goedgekeurde verlof.")
    return sorted(days)


def _cancellation_selected_days(s, request: LeaveCancellation,
                                leave: LeaveRequest) -> list[date]:
    selection = s.get(LeaveCancellationSelection, request.id)
    if selection is None:
        # Bestaande verzoeken uit v0.18.1: volledige intrekking.
        return _remaining_approved_leave_days(s, leave)
    try:
        return [date.fromisoformat(d) for d in selection.days]
    except (TypeError, ValueError) as exc:
        raise ValueError("Opgeslagen verlofdatums zijn ongeldig; laat dit controleren.") from exc


def _save_cancel_selection(s, request_id: int, selected: list[date]) -> None:
    s.add(LeaveCancellationSelection(cancellation_id=request_id,
                                     days=[d.isoformat() for d in selected]))


def _visible_cancel_days(s, cancel: LeaveCancellation, leave: LeaveRequest) -> list[str]:
    selection = s.get(LeaveCancellationSelection, cancel.id)
    if selection is not None:
        return list(selection.days)
    if cancel.status == "pending":
        return [d.isoformat() for d in _remaining_approved_leave_days(s, leave)]
    return [d.isoformat() for d in leave_days(leave.start_date, leave.end_date,
                                              leave.start_date.year, leave.start_date.month)]


def _leave_dict_with_remaining(s, row: LeaveRequest) -> dict:
    result = _leave_dict(row)
    result["remaining_dates"] = [d.isoformat() for d in _remaining_approved_leave_days(s, row)]
    return result


def _approved_leave_protected(s, payload: dict) -> None:
    year, month = int(payload["year"]), int(payload["month"])
    for leave in s.scalars(select(LeaveRequest).where(LeaveRequest.status == "approved")).all():
        if not (leave.start_date.year <= year <= leave.end_date.year):
            continue
        approved = [absence_credit(leave.employee_id, day, leave.hours_per_day)
                    for day in _remaining_approved_leave_days(s, leave)
                    if (day.year, day.month) == (year, month)]
        for entry in approved:
            if entry not in payload.get("hour_credits", []):
                raise ValueError("Een goedgekeurde verlofdag mag niet zomaar gewijzigd of gewist worden.")


def save_month_workspace(engine, payload: dict, expected_revision: int, actor: str,
                         action: str) -> int:
    """Maandgebonden en globale wijzigingen atomair met conflictcontrole.

    Een globale wijziging verhoogt ook de revisie van andere maanden, zodat
    reeds berekende (niet opnieuw gevalideerde) plannen niet meer publiceerbaar zijn.
    """
    year, month = int(payload["year"]), int(payload["month"])
    key = period_key(year, month)
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        shared = s.scalar(select(SharedCatalog).where(SharedCatalog.id == 1).with_for_update())
        row = s.scalar(select(MonthWorkspace).where(MonthWorkspace.period == key).with_for_update())
        if row is None or row.revision != expected_revision or shared is None:
            raise ConflictError("De maandgegevens zijn elders aangepast. Vernieuw en probeer opnieuw.")
        original = merge_shared(row.payload, shared.payload)
        if who.role == "controleur":
            old = deepcopy(original)
            new = deepcopy(payload)
            old_prefs = old.pop("preferences")
            new_prefs = new.pop("preferences")
            if (old != new or
                [p for p in old_prefs if p["employee_id"] != actor] !=
                [p for p in new_prefs if p["employee_id"] != actor]):
                raise ValueError("Controleurs mogen alleen hun eigen voorkeuren aanpassen.")
        elif who.role not in ("admin", "planner"):
            raise ValueError("Geen toegangsrechten.")
        _approved_leave_protected(s, payload)
        new_shared = shared_fields(payload)
        changed_global = new_shared != shared.payload
        if changed_global:
            if who.role == "controleur":
                raise ValueError("Geen rechten om de catalogus te wijzigen.")
            shared.payload = new_shared
            # Maak bestaande concepten ongeldig na gewijzigde gedeelde catalogus.
            for other in s.scalars(select(MonthWorkspace)).all():
                if other.period != key:
                    other.revision += 1
        row.payload = payload
        row.revision += 1
        _audit(s, actor, f"{year}-{month:02d}: {action}" +
               (" (gedeelde catalogus aangepast)" if changed_global else ""))
        return row.revision


def _period_workspace(s, year: int, month: int):
    """v0.12 gebruikt een maandrij; legacy tests zonder migratie gebruiken Workspace."""
    row = s.get(MonthWorkspace, period_key(year, month))
    if row is not None:
        return row
    legacy = s.get(Workspace, 1)
    if legacy and (legacy.payload["year"], legacy.payload["month"]) == (year, month):
        return legacy
    return None


def load_workspace(engine) -> tuple[dict, int]:
    with session_factory(engine)() as s:
        row = s.get(Workspace, 1)
        if row is None:
            raise SetupError("Werkruimte ontbreekt.")
        return row.payload, row.revision


def save_workspace(engine, payload: dict, expected_revision: int, actor: str, action: str) -> int:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        row = s.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
        if row is None or row.revision != expected_revision:
            raise ConflictError("Een andere gebruiker heeft intussen wijzigingen opgeslagen. Vernieuw de pagina en probeer opnieuw.")
        if who.role == "controleur":
            # Alleen eigen zachte voorkeuren; geen enkele wijziging aan de rest.
            old = dict(row.payload)
            new = dict(payload)
            old_prefs = old.pop("preferences")
            new_prefs = new.pop("preferences")
            if old != new or [p for p in old_prefs if p["employee_id"] != actor] != [p for p in new_prefs if p["employee_id"] != actor]:
                raise ValueError("Controleurs mogen uitsluitend hun eigen voorkeuren aanpassen.")
        elif who.role not in ("admin", "planner"):
            raise ValueError("Geen toegangsrechten.")
        # Een reeds goedgekeurde afwezigheid mag niet stilzwijgend uit de
        # werkruimte verdwijnen of van uren veranderen. Corrigeren volgt
        # later via een afzonderlijke, geauditeerde beheerworkflow.
        for leave in s.scalars(select(LeaveRequest).where(LeaveRequest.status == "approved")).all():
            if (leave.start_date.year, leave.start_date.month) != (int(payload["year"]), int(payload["month"])):
                continue
            approved = [absence_credit(leave.employee_id, day, leave.hours_per_day)
                        for day in _remaining_approved_leave_days(s, leave)
                        if (day.year, day.month) == (int(payload["year"]), int(payload["month"]))]
            for entry in approved:
                if entry not in payload.get("hour_credits", []):
                    raise ValueError("Een goedgekeurde verlofdag mag niet zomaar gewijzigd of gewist worden.")
        row.payload = payload
        row.revision += 1
        _audit(s, actor, action)
        return row.revision


def list_accounts(engine) -> list[dict]:
    with session_factory(engine)() as s:
        rows = s.scalars(select(Account).order_by(Account.employee_id)).all()
        return [{k: v for k, v in public_account(a).items() if k != "auth_hash"} for a in rows]


def add_account(engine, employee_id: str, name: str, role: str, temporary_password: str, actor: str) -> None:
    employee_id, name = employee_id.strip(), name.strip()
    if not employee_id or len(employee_id) > 64 or not name or len(name) > 160 or role not in ROLES:
        raise ValueError("Controleer personeelsnummer, naam en rol.")
    check_password_strength(temporary_password)
    try:
        with session_factory(engine).begin() as s:
            who = s.get(Account, actor)
            if who is None or who.role != "admin" or not who.active:
                raise ValueError("Alleen hoofdbeheerders kunnen accounts aanmaken.")
            s.add(Account(employee_id=employee_id, name=name,
                          password_hash=HASHER.hash(temporary_password), role=role,
                          active=True, must_change_password=True, failed_logins=0))
            _audit(s, actor, f"Account aangemaakt: {employee_id} ({role})")
    except IntegrityError as exc:
        raise ValueError("Dit personeelsnummer bestaat al als account.") from exc


def set_account_state(engine, employee_id: str, active: bool, actor: str) -> None:
    if employee_id == actor and not active:
        raise ValueError("Je kunt je eigen account niet deactiveren.")
    with session_factory(engine).begin() as s:
        a = s.get(Account, employee_id)
        if a is None:
            raise ValueError("Onbekend account.")
        who = s.get(Account, actor)
        if who is None or who.role != "admin" or not who.active:
            raise ValueError("Alleen hoofdbeheerders kunnen accounts beheren.")
        if a.role == "admin" and not active:
            # Houd de laatste actieve beheerder altijd actief.
            if s.query(Account).filter(Account.role == "admin", Account.active.is_(True)).count() <= 1:
                raise ValueError("De laatste actieve beheerder kan niet gedeactiveerd worden.")
        a.active = active
        _audit(s, actor, f"Account {'geactiveerd' if active else 'gedeactiveerd'}: {employee_id}")


def reset_password(engine, employee_id: str, new_password: str, actor: str) -> None:
    check_password_strength(new_password)
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if who is None or who.role != "admin" or not who.active:
            raise ValueError("Alleen hoofdbeheerders kunnen wachtwoorden resetten.")
        a = s.get(Account, employee_id)
        if a is None:
            raise ValueError("Onbekend account.")
        a.password_hash = HASHER.hash(new_password)
        a.must_change_password = True
        a.failed_logins = 0
        a.locked_until = None
        _audit(s, actor, f"Wachtwoord opnieuw ingesteld: {employee_id}")


def recover_admin_once(engine, employee_id: str, entered_key: str, new_password: str,
                       configured_key: str) -> None:
    """Herstel één bestaande beheerder met een eenmalig geheim uit Streamlit Secrets.

    De sleutel wordt nooit gelogd of in leesbare vorm in de database opgeslagen.
    Alleen het accountwachtwoord en de blokkadestatus worden gewijzigd; alle andere
    bedrijfsgegevens blijven ongemoeid.
    """
    if len(configured_key) < 32:
        raise ValueError("De herstelcode in Streamlit Secrets moet minstens 32 tekens lang zijn.")
    if not hmac.compare_digest(entered_key.encode("utf-8"), configured_key.encode("utf-8")):
        raise ValueError("Herstelcode onjuist.")
    check_password_strength(new_password)
    digest = hashlib.sha256(configured_key.encode("utf-8")).hexdigest()

    with session_factory(engine).begin() as s:
        if s.get(UsedRecoveryKey, digest) is not None:
            raise ValueError("Deze herstelcode is al gebruikt. Verwijder hem uit Streamlit Secrets.")
        # Toewijzing en codeverbruik gebeuren in één database-transactie.
        admin = s.scalar(select(Account).where(Account.employee_id == employee_id).with_for_update())
        if admin is None or admin.role != "admin" or not admin.active:
            raise ValueError("Geen actief beheerdersaccount gevonden met dit personeelsnummer.")
        s.add(UsedRecoveryKey(key_digest=digest, used_at=now(), admin_id=employee_id))
        s.flush()  # Unieke sleutel voorkomt gelijktijdig hergebruik.
        admin.password_hash = HASHER.hash(new_password)
        admin.must_change_password = False
        admin.failed_logins = 0
        admin.locked_until = None
        _audit(s, employee_id, "Eenmalig beheerderswachtwoord hersteld")


def change_password(engine, employee_id: str, old_password: str, new_password: str) -> None:
    check_password_strength(new_password)
    with session_factory(engine).begin() as s:
        a = s.scalar(select(Account).where(Account.employee_id == employee_id).with_for_update())
        if a is None or not a.active:
            raise ValueError("Account niet beschikbaar.")
        try:
            verified = HASHER.verify(a.password_hash, old_password)
        except (VerifyMismatchError, VerificationError, ValueError):
            verified = False
        if not verified:
            raise ValueError("Huidig wachtwoord is niet correct.")
        if old_password == new_password:
            raise ValueError("Kies een ander wachtwoord.")
        a.password_hash = HASHER.hash(new_password)
        a.must_change_password = False
        a.failed_logins = 0
        a.locked_until = None
        _audit(s, employee_id, "Eigen wachtwoord gewijzigd")


def _published_boundary_ids(s, year: int, month: int) -> dict:
    """Nieuwste gepubliceerde versies in de twee aangrenzende maanden."""
    from boundary_v015 import adjacent_months
    result = {}
    for side, (y, m) in adjacent_months(year, month).items():
        row = _current_published(s, y, m)
        result[side] = row.id if row else None
    return result


def _assert_boundary_current(s, year: int, month: int, payload: dict) -> None:
    saved_sources = (payload.get("summary") or {}).get("boundary_sources")
    if saved_sources is not None and saved_sources != _published_boundary_ids(s, year, month):
        raise ConflictError("Een gepubliceerde aangrenzende maand is gewijzigd. "
                            "Bereken de planning opnieuw om de rustregels te controleren.")


def _verify_marked_result_v025(s, data: dict, result: dict) -> None:
    """Nieuw berekende v0.25-concepten nogmaals onafhankelijk controleren.

    Bestaande historische planrecords zonder v0.25-kenmerk blijven leesbaar;
    nieuwe webberekeningen krijgen het kenmerk vanuit app.py.
    """
    summary = result.get("summary") if isinstance(result, dict) else None
    if not isinstance(summary, dict) or "validation_v025" not in summary:
        return
    from boundary_v015 import adjacent_months
    from validator_v025 import verify_plan
    adjacent = adjacent_months(int(data["year"]), int(data["month"]))
    rows = []
    for side, (year, month) in adjacent.items():
        published = _current_published(s, year, month)
        if published is None:
            continue
        for r in published.payload.get("assignments", []):
            rows.append({"employee_id": str(r["Personeelsnr"]),
                         "date": str(r["Datum"]), "start": str(r["Begin"]),
                         "end": str(r["Einde"]), "category": str(r["Categorie"]),
                         "source": side})
    check = verify_plan(data, result, rows)
    if not check["passed"]:
        raise ValueError("Onafhankelijke roostercontrole v0.25 mislukt: "
                         + "; ".join(check["errors"][:5]))


def save_plan(engine, data: dict, workspace_revision: int, result: dict, actor: str,
              expected_latest_plan_id: int | None = None) -> int:
    """Sla een concept op; v0.23 kan een inmiddels gewijzigde bronversie afwijzen."""
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if who is None or who.role not in ("admin", "planner") or not who.active:
            raise ValueError("Geen rechten om een planning te berekenen.")
        w = _period_workspace(s, int(data["year"]), int(data["month"]))
        if w is None or w.revision != workspace_revision:
            raise ConflictError("De invoergegevens zijn tijdens de berekening veranderd. Vernieuw en bereken opnieuw.")
        if expected_latest_plan_id is not None:
            latest_id = s.scalar(select(PlanningVersion.id).where(
                PlanningVersion.year == data["year"],
                PlanningVersion.month == data["month"]
            ).order_by(PlanningVersion.id.desc()).limit(1))
            if latest_id != expected_latest_plan_id:
                raise ConflictError("Er is intussen een nieuwere planversie gemaakt. "
                                    "Ververs de pagina en controleer je handmatige wijzigingen opnieuw.")
        _assert_boundary_current(s, int(data["year"]), int(data["month"]), result)
        _verify_marked_result_v025(s, w.payload, result)
        row = PlanningVersion(workspace_revision=workspace_revision, year=data["year"], month=data["month"],
                              author=actor, created_at=now(), payload=result)
        s.add(row)
        s.flush()
        _audit(s, actor, f"Conceptplanning {data['year']}-{data['month']:02d} v{row.id} berekend")
        return row.id


def load_plan(engine, year: int, month: int, published_only: bool = False) -> dict | None:
    with session_factory(engine)() as s:
        q = select(PlanningVersion).where(PlanningVersion.year == year, PlanningVersion.month == month)
        if published_only:
            q = q.where(PlanningVersion.published_at.is_not(None)).order_by(PlanningVersion.published_at.desc(), PlanningVersion.id.desc())
        else:
            q = q.order_by(PlanningVersion.id.desc())
        row = s.scalar(q.limit(1))
        if row is None:
            return None
        return {"id": row.id, "payload": row.payload, "revision": row.workspace_revision,
                "published": bool(row.published_at), "author": row.author}



def personal_published_versions(engine, year: int, month: int, actor: str,
                                employee_id: str | None = None, limit: int = 2) -> list[dict]:
    """Maximaal twee gepubliceerde versies, beveiligd per ingelogde gebruiker.

    Controleurs kunnen uitsluitend hun eigen diensttoewijzingen opvragen. Een
    planner/beheerder mag een specifieke controleur kiezen. Andere
    persoonsgegevens en eventuele ruwe solvergegevens verlaten de DB niet.
    """
    if limit < 1 or limit > 2:
        raise ValueError("Ongeldig aantal planningsversies.")
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        target = employee_id or actor
        if who.role == "controleur" and target != actor:
            raise ValueError("Controleurs kunnen alleen hun eigen planning bekijken.")
        if who.role not in ("controleur", "admin", "planner"):
            raise ValueError("Geen toegangsrechten.")
        q = (select(PlanningVersion).where(
            PlanningVersion.year == year, PlanningVersion.month == month,
            PlanningVersion.published_at.is_not(None))
            .order_by(PlanningVersion.published_at.desc(), PlanningVersion.id.desc())
            .limit(limit))
        result = []
        for published in s.scalars(q).all():
            payload = published.payload if isinstance(published.payload, dict) else {}
            assignments = payload.get("assignments")
            if not isinstance(assignments, list):
                assignments = []
            result.append({"id": published.id,
                           "published_at": published.published_at.isoformat(),
                           "assignments": [dict(r) for r in assignments
                                           if isinstance(r, dict) and r.get("Personeelsnr") == target]})
        return result

def publication_preview(engine, plan_id: int, actor: str) -> dict:
    """Beveiligd voorbeeld: status en verschillen tegenover vorige publicatie."""
    from portal_v017 import personal_publication_changes
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Geen publicatierechten.")
        row = s.get(PlanningVersion, plan_id)
        if row is None:
            raise ValueError("Planningsversie onbekend.")
        earlier = _current_published(s, row.year, row.month)
        current = row.payload.get("assignments", []) if isinstance(row.payload, dict) else []
        previous = earlier.payload.get("assignments", []) if earlier and isinstance(earlier.payload, dict) else []
        ids = {r.get("Personeelsnr") for r in (previous + current) if isinstance(r, dict)}
        ids.discard(None)
        affected = sum(bool(personal_publication_changes(previous, current, eid)) for eid in ids)
        summary = row.payload.get("summary", {}) if isinstance(row.payload, dict) else {}
        open_places = summary.get("open") if isinstance(summary, dict) else None
        return {"id": row.id, "year": row.year, "month": row.month,
                "already_published": row.published_at is not None,
                "last_published_id": earlier.id if earlier else None,
                "affected_controllers": affected,
                "open_positions": open_places,
                "status": row.payload.get("status") if isinstance(row.payload, dict) else None}


def publish_plan(engine, plan_id: int, expected_revision: int, actor: str) -> None:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if who is None or who.role not in ("admin", "planner") or not who.active:
            raise ValueError("Geen rechten om een planning te publiceren.")
        row = s.scalar(select(PlanningVersion).where(PlanningVersion.id == plan_id).with_for_update())
        w = _period_workspace(s, row.year, row.month) if row else None
        if row is None or w is None or w.revision != expected_revision or row.workspace_revision != expected_revision:
            raise ConflictError("Deze planning is verouderd. Bereken opnieuw met de actuele invoergegevens.")
        if row.published_at is not None:
            raise ValueError("Deze versie is al gepubliceerd.")
        _assert_boundary_current(s, row.year, row.month, row.payload)
        if row.payload.get("status") not in ("OPTIMAL", "FEASIBLE"):
            raise ValueError("Er is geen geldige planning om te publiceren.")
        _verify_marked_result_v025(s, w.payload, row.payload)
        earlier = _current_published(s, row.year, row.month)
        row.published_at = now()
        s.flush()
        _publish_notifications(s, row, earlier)
        _audit(s, actor, f"Planning versie {plan_id} gepubliceerd")


def recent_audit(engine, count: int = 100) -> list[dict]:
    with session_factory(engine)() as s:
        rows = s.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(count)).all()
        return [{"Tijdstip (UTC)": a.created_at.isoformat(), "Gebruiker": a.actor, "Actie": a.action} for a in rows]


def published_plans_before(engine, year: int, month: int, months_back: int = 3) -> list[dict]:
    """Laatste GEPUBLICEERDE versie per vroegere maand binnen het kijkvenster.

    Read-only; concepten en planningen voor de doelmaand tellen niet mee.
    """
    if not 1 <= months_back <= 12:
        raise ValueError('Kijkvenster moet 1–12 maanden zijn.')
    target = year * 12 + month - 1
    with session_factory(engine)() as s:
        rows = s.scalars(
            select(PlanningVersion)
            .where(PlanningVersion.published_at.is_not(None))
            .order_by(PlanningVersion.published_at.desc(), PlanningVersion.id.desc())
        ).all()
        found = {}
        for row in rows:
            period = row.year * 12 + row.month - 1
            if target - months_back <= period < target:
                found.setdefault(period, row)
        return [{'year': p.year, 'month': p.month, 'id': p.id, 'payload': p.payload}
                for _, p in sorted(found.items())]


def report_published_window(engine, actor: str, year: int, month: int,
                            months_back: int = 3) -> list[dict]:
    """Latest published version for each calendar month, scoped to admin/planner.

    Read-only and never returns drafts. This is NOT a personnel self-service API.
    """
    if type(year) is not int or type(month) is not int or not 1 <= month <= 12:
        raise ValueError("Ongeldige rapportmaand.")
    if type(months_back) is not int or not 1 <= months_back <= 12:
        raise ValueError("Het rapportvenster moet 1 tot 12 maanden zijn.")
    target = year * 12 + month - 1
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Geen rechten om teamrapporten te raadplegen.")
        # Beperk de query tot de relevante kalenderjaren. De periodecontrole
        # in Python vermijdt verschillen in SQL-aritmetiek tussen databases.
        first_year = (target - months_back + 1) // 12
        versions = s.scalars(select(PlanningVersion).where(
            PlanningVersion.published_at.is_not(None),
            PlanningVersion.year >= first_year,
            PlanningVersion.year <= year,
        ).order_by(PlanningVersion.published_at.desc(), PlanningVersion.id.desc())).all()
        latest = {}
        for row in versions:
            period = row.year * 12 + row.month - 1
            if target - months_back < period <= target:
                latest.setdefault((row.year, row.month), row)
        return [dict(year=r.year, month=r.month, id=r.id, revision=r.workspace_revision,
                     payload=r.payload if isinstance(r.payload, dict) else {})
                for _, r in sorted(latest.items())]


def _leave_dict(row: LeaveRequest) -> dict:
    return {"id": row.id, "employee_id": row.employee_id,
            "start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(),
            "status": row.status, "created_at": row.created_at.isoformat(),
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "decided_by": row.decided_by, "hours_per_day": row.hours_per_day}


def request_leave(engine, employee_id: str, start: date, end: date) -> int:
    """Controleur vraagt alleen eigen verlof aan voor de actieve testmaand."""
    with session_factory(engine).begin() as s:
        who = s.get(Account, employee_id)
        if who is None or who.role != "controleur" or not who.active:
            raise ValueError("Alleen een actieve controleur kan eigen verlof aanvragen.")
        w = _period_workspace(s, start.year, start.month)
        if w is None or (start.year, start.month) != (end.year, end.month):
            raise ValueError("Kies een periode binnen één aangemaakte planningsmaand.")
        state = merge_shared(w.payload, s.get(SharedCatalog, 1).payload) if isinstance(w, MonthWorkspace) else w.payload
        if not any(e["id"] == employee_id and e.get("active", True)
                   for e in state["employees"]):
            raise ValueError("Dit account is niet aan een actieve controleur gekoppeld.")
        dates = leave_days(start, end, int(state["year"]), int(state["month"]))
        for other in s.scalars(select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status.in_(("pending", "approved")))).all():
            if other.status == "pending" and start <= other.end_date and other.start_date <= end:
                raise ValueError("Er bestaat al een openstaande aanvraag voor deze dagen.")
            if other.status == "approved" and set(dates) & set(_remaining_approved_leave_days(s, other)):
                raise ValueError("Er bestaat al goedgekeurd verlof voor deze dagen.")
        existing = {(c["employee_id"], c["date"]) for c in w.payload.get("hour_credits", [])}
        if any((employee_id, day.isoformat()) in existing for day in dates):
            raise ValueError("Op één of meer aangevraagde dagen staat al een geregistreerde afwezigheid.")
        row = LeaveRequest(employee_id=employee_id, start_date=start, end_date=end,
                           status="pending", created_at=now())
        s.add(row)
        s.flush()
        _notify_managers(s, f"leave-pending:{row.id}", "Nieuwe verlofaanvraag",
                         f"Verlofaanvraag #{row.id} wacht op behandeling. "
                         "Open Verlofaanvragen beheren.")
        _audit(s, employee_id, f"Verlofaanvraag #{row.id} ingediend")
        return row.id


def list_leave_requests(engine, actor: str) -> list[dict]:
    """Toegangstechnisch afgedwongen: controleurs zien alleen eigen aanvragen."""
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        query = select(LeaveRequest).order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
        if who.role == "controleur":
            query = query.where(LeaveRequest.employee_id == actor)
        elif who.role not in ("admin", "planner"):
            raise ValueError("Geen toegangsrechten.")
        return [_leave_dict_with_remaining(s, r) for r in s.scalars(query).all()]


def withdraw_leave_request(engine, request_id: int, actor: str) -> None:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        row = s.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
        if not who or not who.active or who.role != "controleur" or not row or row.employee_id != actor:
            raise ValueError("Je kunt alleen je eigen aanvraag intrekken.")
        if row.status != "pending":
            raise ValueError("Alleen een openstaande aanvraag kan ingetrokken worden.")
        row.status = "withdrawn"
        row.decided_at = now()
        row.decided_by = actor
        _audit(s, actor, f"Verlofaanvraag #{row.id} ingetrokken")


def decide_leave_request(engine, request_id: int, actor: str, approve: bool,
                         hours_per_day: float = 0.0) -> dict:
    """Atomair goedkeuren + registreren: nooit deels een goedgekeurde aanvraag.

    Alleen goedgekeurde aanvragen blokkeren de solver; de gepubliceerde planning
    wordt NOOIT op de achtergrond gewijzigd en moet opnieuw berekend worden.
    """
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Alleen beheerders of planners mogen beslissen.")
        row = s.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
        w = _period_workspace(s, row.start_date.year, row.start_date.month) if row else None
        if not row or row.status != "pending":
            raise ValueError("Deze aanvraag is niet meer in behandeling.")
        if w is None:
            raise ValueError("Werkruimte ontbreekt.")
        state = merge_shared(w.payload, s.get(SharedCatalog, 1).payload) if isinstance(w, MonthWorkspace) else w.payload
        days = leave_days(row.start_date, row.end_date,
                          int(state["year"]), int(state["month"]))
        if approve:
            if not isinstance(hours_per_day, (int, float)) or not 0 <= hours_per_day <= 16:
                raise ValueError("Testuren moeten tussen 0 en 16 liggen.")
            if not any(e["id"] == row.employee_id and e.get("active", True)
                       for e in state["employees"]):
                raise ValueError("Controleur bestaat niet meer of is niet actief.")
            payload = dict(state)
            credits = list(payload.get("hour_credits", []))
            existing = {(c["employee_id"], c["date"]) for c in credits}
            additions = [absence_credit(row.employee_id, day, float(hours_per_day)) for day in days]
            if any((entry["employee_id"], entry["date"]) in existing for entry in additions):
                raise ValueError("Op één of meer dagen staat al een activiteit. Controleer eerst het urenoverzicht.")
            credits.extend(additions)
            payload["hour_credits"] = credits
            # De regelvalidatie bevat geen OR-Tools-import: bruikbaar in databasetests.
            from extras import validate_extras
            problems = validate_extras(payload)
            if problems:
                raise ValueError("Afwezigheid kan niet worden verwerkt: " + " ".join(problems))
            w.payload = payload
            w.revision += 1
            row.hours_per_day = float(hours_per_day)
            row.status = "approved"
        else:
            row.status = "rejected"
        row.decided_at = now()
        row.decided_by = actor
        _notice(s, row.employee_id, f"leave-decision:{row.id}:{row.status}",
                "Beslissing verlofaanvraag", f"Je verlofaanvraag #{row.id} is "
                + ("goedgekeurd" if approve else "afgewezen") + ".")
        _audit(s, actor, f"Verlofaanvraag #{row.id} {row.status} door {actor}")
        return {"id": row.id, "status": row.status, "workspace_revision": w.revision}


# v0.18.1 — Intrekken van reeds goedgekeurd verlof, met toestemming en historiek.

def _cancellation_dict(row: LeaveCancellation) -> dict:
    return {"id": row.id, "leave_request_id": row.leave_request_id,
            "requested_by": row.requested_by, "reason": row.reason,
            "status": row.status, "created_at": row.created_at.isoformat(),
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "decided_by": row.decided_by}


def list_leave_cancellations(engine, actor: str) -> list[dict]:
    """Een controleur ziet alleen de intrekkingen van eigen verlof."""
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        q = select(LeaveCancellation, LeaveRequest).join(
            LeaveRequest, LeaveCancellation.leave_request_id == LeaveRequest.id)
        if who.role == "controleur":
            q = q.where(LeaveRequest.employee_id == actor)
        elif who.role not in ("admin", "planner"):
            raise ValueError("Geen toegangsrechten.")
        q = q.order_by(LeaveCancellation.id.desc())
        return [{**_cancellation_dict(cancel),
                 "employee_id": leave.employee_id,
                 "start_date": leave.start_date.isoformat(),
                 "end_date": leave.end_date.isoformat(),
                 "selected_dates": _visible_cancel_days(s, cancel, leave)}
                for cancel, leave in s.execute(q).all()]


def _validate_cancel_reason(reason: str) -> str:
    reason = str(reason or "").strip()
    if not 5 <= len(reason) <= 400:
        raise ValueError("Vermeld een korte reden (5 tot 400 tekens).")
    return reason


def request_leave_cancellation(engine, request_id: int, actor: str, reason: str,
                               days: list[date] | None = None) -> int:
    """Controleur verzoekt intrekking van een selectie, zonder directe gevolgen voor de planning.

    days=None blijft achterwaarts compatibel: alle nog goedgekeurde dagen.
    """
    reason = _validate_cancel_reason(reason)
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        leave = s.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
        if not who or not who.active or who.role != "controleur" or not leave or leave.employee_id != actor:
            raise ValueError("Alleen de betrokken controleur kan een intrekking aanvragen.")
        if leave.status != "approved":
            raise ValueError("Alleen goedgekeurd verlof kan via dit verzoek worden ingetrokken.")
        remaining = _remaining_approved_leave_days(s, leave)
        selected = _validate_leave_cancel_days(leave, remaining, days)
        pending = s.scalar(select(LeaveCancellation.id).where(
            LeaveCancellation.leave_request_id == request_id,
            LeaveCancellation.status == "pending").limit(1))
        if pending:
            raise ValueError("Voor dit verlof bestaat al een intrekkingsverzoek.")
        row = LeaveCancellation(leave_request_id=request_id, requested_by=actor,
                                reason=reason, status="pending", created_at=now())
        s.add(row)
        s.flush()
        _save_cancel_selection(s, row.id, selected)
        _notify_managers(s, f"leave-cancel-pending:{row.id}", "Verzoek om verlof in te trekken",
                         f"Intrekkingsverzoek #{row.id} voor {len(selected)} dag(en) van "
                         f"goedgekeurd verlof #{request_id} wacht op beslissing.")
        _audit(s, actor, f"Intrekking van {len(selected)} verlofdag(en) uit #{request_id} "
                         f"aangevraagd (verzoek #{row.id})")
        return row.id


def _apply_approved_leave_cancellation(s, leave: LeaveRequest, actor: str,
                                       selected: list[date]) -> int:
    """Atomair uitsluitend de expliciet geselecteerde, nog actieve verlofdagen verwijderen."""
    # Lock de maandrij mee om gelijktijdige wijzigingen aan afwezigheden
    # op PostgreSQL niet verloren te laten gaan.
    w = s.scalar(select(MonthWorkspace).where(
        MonthWorkspace.period == period_key(leave.start_date.year, leave.start_date.month)
    ).with_for_update())
    if w is None:
        w = s.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
        if w and (w.payload["year"], w.payload["month"]) != (
                leave.start_date.year, leave.start_date.month):
            w = None
    if w is None:
        raise ValueError("De bijbehorende maandplanning bestaat niet meer.")
    if leave.status != "approved":
        raise ValueError("Het verlof is niet langer goedgekeurd.")
    remaining = _remaining_approved_leave_days(s, leave)
    selected = _validate_leave_cancel_days(leave, remaining, selected)
    state = deepcopy(w.payload)
    credits = state.get("hour_credits", [])
    if not isinstance(credits, list):
        raise ValueError("De afwezigheden van deze maand zijn ongeldig.")
    expected = [absence_credit(leave.employee_id, day, float(leave.hours_per_day))
                for day in selected]
    # Eerst de volledige selectie controleren, dan pas de payload wijzigen.
    available = deepcopy(credits)
    for entry in expected:
        if entry not in available:
            raise ValueError("De goedgekeurde verlofregistratie is gewijzigd. Controleer eerst de activiteiten.")
        available.remove(entry)
    state["hour_credits"] = available
    w.payload = state
    w.revision += 1
    if set(selected) == set(remaining):
        leave.status = "cancelled"
    _audit(s, actor, f"{len(selected)} verlofdag(en) uit goedgekeurd verlof #{leave.id} "
                     f"ingetrokken; maandrevisie {w.revision}")
    return w.revision


def decide_leave_cancellation(engine, cancellation_id: int, actor: str, approve: bool) -> dict:
    """Planner/administrator beslist. Bij goedkeuring vervalt de blokkering, niet de publicatie."""
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Alleen beheerders of planners mogen beslissen.")
        # Eerst de verlofrij vergrendelen, dan het verzoek (dezelfde volgorde
        # als bij rechtstreekse intrekking door een beheerder).
        reference = s.get(LeaveCancellation, cancellation_id)
        if not reference or reference.status != "pending":
            raise ValueError("Dit intrekkingsverzoek is niet meer in behandeling.")
        leave = s.scalar(select(LeaveRequest).where(
            LeaveRequest.id == reference.leave_request_id).with_for_update())
        if not leave or leave.status != "approved":
            raise ValueError("Dit verlof is niet meer goedgekeurd.")
        request = s.scalar(select(LeaveCancellation).where(
            LeaveCancellation.id == cancellation_id).with_for_update())
        if not request or request.status != "pending":
            raise ValueError("Dit intrekkingsverzoek is al verwerkt.")
        revision = None
        selected = _cancellation_selected_days(s, request, leave)
        if approve:
            revision = _apply_approved_leave_cancellation(s, leave, actor, selected)
        request.status = "approved" if approve else "rejected"
        request.decided_at = now()
        request.decided_by = actor
        _notice(s, leave.employee_id, f"leave-cancel-decision:{request.id}",
                "Beslissing intrekking verlof",
                f"Je verzoek om {len(selected)} dag(en) van verlof #{leave.id} in te trekken is "
                + ("goedgekeurd. Een reeds gepubliceerd rooster wordt niet automatisch gewijzigd."
                   if approve else "afgewezen. Het goedgekeurde verlof blijft behouden."))
        _audit(s, actor, f"Intrekkingsverzoek #{request.id} voor verlof #{leave.id} "
               + ("goedgekeurd" if approve else "afgewezen"))
        return {"id": request.id, "status": request.status, "workspace_revision": revision}


def revoke_approved_leave(engine, request_id: int, actor: str, reason: str,
                          days: list[date] | None = None) -> dict:
    """Beheerder verwerkt een extern verzoek (geheel of een aantal dagen).

    Een al openstaand verzoek wordt alleen als datzelfde verzoek verwerkt; een
    afwijkende selectie moet via dat oorspronkelijke verzoek behandeld worden.
    """
    reason = _validate_cancel_reason(reason)
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Alleen beheerders of planners mogen verlof intrekken.")
        leave = s.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
        if not leave or leave.status != "approved":
            raise ValueError("Alleen goedgekeurd verlof kan ingetrokken worden.")
        selected = _validate_leave_cancel_days(leave, _remaining_approved_leave_days(s, leave), days)
        pending = s.scalar(select(LeaveCancellation).where(
            LeaveCancellation.leave_request_id == request_id,
            LeaveCancellation.status == "pending").with_for_update())
        if pending:
            request = pending
            requested = _cancellation_selected_days(s, request, leave)
            if days is not None and set(requested) != set(selected):
                raise ValueError("Behandel het bestaande intrekkingsverzoek; de geselecteerde dagen wijken af.")
            selected = requested
        else:
            request = LeaveCancellation(leave_request_id=request_id,
                                        requested_by=actor, reason=reason,
                                        status="pending", created_at=now())
            s.add(request)
            s.flush()
            _save_cancel_selection(s, request.id, selected)
        revision = _apply_approved_leave_cancellation(s, leave, actor, selected)
        request.status = "approved"
        request.decided_at = now()
        request.decided_by = actor
        _notice(s, leave.employee_id, f"leave-cancel-decision:{request.id}",
                "Goedgekeurd verlof ingetrokken",
                f"{len(selected)} dag(en) van goedgekeurd verlof #{leave.id} "
                "werden door de beheerder ingetrokken. Een gepubliceerd rooster "
                "blijft ongewijzigd tot een nieuwe publicatie.")
        _audit(s, actor, f"Rechtstreekse intrekking {len(selected)} dag(en) uit verlof #{leave.id}: {reason[:80]}")
        return {"id": request.id, "status": request.status, "workspace_revision": revision}


# v0.11 — Onderlinge dienstwissels, enkel met fictieve gegevens.

def _current_published(s, year: int, month: int) -> PlanningVersion | None:
    return s.scalar(select(PlanningVersion).where(
        PlanningVersion.year == year, PlanningVersion.month == month,
        PlanningVersion.published_at.is_not(None)
    ).order_by(PlanningVersion.published_at.desc(), PlanningVersion.id.desc()).limit(1))


def _swap_dict(r: SwapRequest) -> dict:
    return {"id": r.id, "plan_id": r.plan_id, "initiator_id": r.initiator_id,
            "colleague_id": r.colleague_id, "own_day": r.own_day.isoformat(),
            "own_shift": r.own_shift, "their_day": r.their_day.isoformat(),
            "their_shift": r.their_shift, "status": r.status,
            "created_at": r.created_at.isoformat(),
            "responded_at": r.responded_at.isoformat() if r.responded_at else None,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "decided_by": r.decided_by, "new_plan_id": r.new_plan_id}


def request_swap(engine, actor: str, colleague: str, own_day: date, own_shift: str,
                 their_day: date, their_shift: str) -> int:
    """Geen teamrooster nodig voor de controleur: hij geeft collega-id en dienst op."""
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        other = s.get(Account, colleague)
        if not who or who.role != "controleur" or not who.active:
            raise ValueError("Alleen actieve controleurs kunnen een ruil voorstellen.")
        if not other or not other.active or other.role != "controleur" or other.employee_id == actor:
            raise ValueError("De voorgestelde ruil is niet mogelijk. Controleer de gegevens.")
        w = _period_workspace(s, own_day.year, own_day.month)
        if w is None:
            raise SetupError("De opgegeven planningsmaand ontbreekt.")
        y, m = int(w.payload["year"]), int(w.payload["month"])
        if any((day.year, day.month) != (y, m) for day in (own_day, their_day)):
            raise ValueError("Een ruil moet binnen de actieve planningsmaand vallen.")
        published = _current_published(s, y, m)
        if published is None or published.workspace_revision != w.revision:
            raise ValueError("Er is geen actuele gepubliceerde planning beschikbaar.")
        make_swap_plan(published.payload, actor, colleague,
                       own_day.isoformat(), str(own_shift), their_day.isoformat(), str(their_shift))
        existing = s.scalars(select(SwapRequest).where(
            SwapRequest.status.in_(("pending", "accepted")),
            SwapRequest.plan_id == published.id)).all()
        touched = {(actor, own_day, str(own_shift)), (colleague, their_day, str(their_shift))}
        for r in existing:
            other_slots = {(r.initiator_id, r.own_day, r.own_shift),
                           (r.colleague_id, r.their_day, r.their_shift)}
            if touched & other_slots:
                raise ValueError("Voor een van deze dienstplaatsen is al een ruilaanvraag in behandeling.")
        row = SwapRequest(plan_id=published.id, initiator_id=actor, colleague_id=colleague,
                          own_day=own_day, own_shift=str(own_shift),
                          their_day=their_day, their_shift=str(their_shift),
                          status="pending", created_at=now())
        s.add(row)
        s.flush()
        _notice(s, colleague, f"swap-request:{row.id}:{colleague}",
                "Nieuw ruilvoorstel", f"Je hebt ruilvoorstel #{row.id} ontvangen. "
                "Open Mijn ruilaanvragen om te reageren.")
        _audit(s, actor, f"Ruilaanvraag #{row.id} ingediend")
        return row.id


def list_swap_requests(engine, actor: str) -> list[dict]:
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        if not who or not who.active:
            raise ValueError("Geen toegangsrechten.")
        q = select(SwapRequest).order_by(SwapRequest.created_at.desc(), SwapRequest.id.desc())
        if who.role == "controleur":
            from sqlalchemy import or_
            q = q.where(or_(SwapRequest.initiator_id == actor, SwapRequest.colleague_id == actor))
        elif who.role not in ("admin", "planner"):
            raise ValueError("Geen toegangsrechten.")
        return [_swap_dict(r) for r in s.scalars(q).all()]


def respond_swap(engine, request_id: int, actor: str, accept: bool) -> None:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        r = s.scalar(select(SwapRequest).where(SwapRequest.id == request_id).with_for_update())
        if not who or not who.active or who.role != "controleur" or r is None:
            raise ValueError("Aanvraag niet beschikbaar.")
        if r.status != "pending":
            raise ValueError("Deze aanvraag is niet meer in behandeling.")
        if actor == r.initiator_id:
            if accept:
                raise ValueError("Je kunt je eigen aanvraag niet goedkeuren.")
            r.status = "withdrawn"
        elif actor == r.colleague_id:
            r.status = "accepted" if accept else "declined"
        else:
            raise ValueError("Je hebt geen toegang tot deze aanvraag.")
        r.responded_at = now()
        _notice(s, r.initiator_id, f"swap-response:{r.id}:{r.status}",
                "Reactie op ruilvoorstel", f"Je ruilvoorstel #{r.id}: "
                + {"withdrawn": "ingetrokken", "accepted": "collega akkoord; wacht op beheerder",
                   "declined": "collega heeft geweigerd"}[r.status] + ".")
        if r.status == "accepted":
            _notify_managers(s, f"swap-accepted:{r.id}", "Ruilaanvraag klaar voor beoordeling",
                             f"Ruilaanvraag #{r.id}: beide controleurs akkoord. "
                             "Open Ruilaanvragen beheren.")
        _audit(s, actor, f"Ruilaanvraag #{r.id} status: {r.status}")


def decide_swap(engine, request_id: int, actor: str, approve: bool, validator=None) -> dict:
    """Eerst buiten DB-transactie solvervalidatie, daarna atomair publiceren.

    Controleer na het rekenen opnieuw dezelfde gepubliceerde versie en revisie.
    """
    with session_factory(engine)() as s:
        who = s.get(Account, actor)
        r = s.get(SwapRequest, request_id)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Geen beheerrechten.")
        if r is None or r.status != "accepted":
            raise ValueError("De collega moet eerst akkoord gaan.")
        w = _period_workspace(s, r.own_day.year, r.own_day.month)
        if w is None:
            raise SetupError("De betreffende planningsmaand ontbreekt.")
        published = _current_published(s, int(w.payload["year"]), int(w.payload["month"]))
        if published is None or published.id != r.plan_id or published.workspace_revision != w.revision:
            raise ConflictError("De gepubliceerde planning is gewijzigd. Deze ruil is verouderd.")
        current_rev, source_plan = w.revision, published.payload
        candidate = make_swap_plan(source_plan, r.initiator_id, r.colleague_id,
                                   r.own_day.isoformat(), r.own_shift,
                                   r.their_day.isoformat(), r.their_shift)
        workspace_snapshot = (merge_shared(w.payload, s.get(SharedCatalog, 1).payload)
                              if isinstance(w, MonthWorkspace) else w.payload)
        old_id = published.id
        boundary_snapshot = _published_boundary_ids(s, published.year, published.month)
    if approve:
        from boundary_v015 import with_boundary_context, published_boundary_context
        context = published_boundary_context(engine, r.own_day.year, r.own_day.month)
        if context["sources"] != boundary_snapshot:
            raise ConflictError("Een buurplanning is tijdens de voorbereiding gewijzigd. Probeer opnieuw.")
        validated_workspace = with_boundary_context(workspace_snapshot, context)
        (validator or verify_swap_with_solver)(validated_workspace, candidate, source_plan)
    with session_factory(engine).begin() as s:
        r = s.scalar(select(SwapRequest).where(SwapRequest.id == request_id).with_for_update())
        w = _period_workspace(s, r.own_day.year, r.own_day.month) if r else None
        who = s.get(Account, actor)
        if not who or not who.active or who.role not in ("admin", "planner"):
            raise ValueError("Geen beheerrechten.")
        if w is None or w.revision != current_rev or r is None or r.status != "accepted":
            raise ConflictError("De aanvraag of invoer is tussentijds gewijzigd.")
        published = _current_published(s, int(w.payload["year"]), int(w.payload["month"]))
        if published is None or published.id != old_id or published.workspace_revision != w.revision:
            raise ConflictError("De gepubliceerde planning is ondertussen gewijzigd.")
        if approve:
            if _published_boundary_ids(s, published.year, published.month) != boundary_snapshot:
                raise ConflictError("Een aangrenzende gepubliceerde planning is intussen gewijzigd.")
            candidate.setdefault("summary", {})["boundary_sources"] = boundary_snapshot
            # Verhoog de revisie om oude concepten en al berekende alternatieven te
            # blokkeren voor herpublicatie na deze ruil. Payload zelf blijft gelijk.
            w.revision += 1
            new_version = PlanningVersion(workspace_revision=w.revision, year=published.year,
                                          month=published.month, author=actor, created_at=now(),
                                          published_at=now(), payload=candidate)
            s.add(new_version)
            s.flush()
            r.new_plan_id = new_version.id
            r.status = "approved"
        else:
            r.status = "rejected"
        r.decided_at = now()
        r.decided_by = actor
        for recipient_id in {r.initiator_id, r.colleague_id}:
            _notice(s, recipient_id, f"swap-decision:{r.id}:{r.status}:{recipient_id}",
                    "Beslissing ruilaanvraag", f"Ruilaanvraag #{r.id} is "
                    + ("goedgekeurd en gepubliceerd" if approve else "afgewezen") + ".")
        _audit(s, actor, f"Ruilaanvraag #{r.id} {r.status}" +
               (f"; nieuwe planversie {r.new_plan_id}" if r.new_plan_id else ""))
        return _swap_dict(r)
