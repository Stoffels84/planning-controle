"""Datalaag voor de v0.2-proefversie (PostgreSQL of lokale SQLite-test).

Geen echte personeelsgegevens gebruiken op gratis Community Cloud zonder goedkeuring.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.exc import IntegrityError

from demo_data import build_demo
from requests_v010 import leave_days, absence_credit


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
                        for day in leave_days(leave.start_date, leave.end_date,
                                              int(payload["year"]), int(payload["month"]))]
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


def save_plan(engine, data: dict, workspace_revision: int, result: dict, actor: str) -> int:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if who is None or who.role not in ("admin", "planner") or not who.active:
            raise ValueError("Geen rechten om een planning te berekenen.")
        w = s.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
        if w is None or w.revision != workspace_revision:
            raise ConflictError("De invoergegevens zijn tijdens de berekening veranderd. Vernieuw en bereken opnieuw.")
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


def publish_plan(engine, plan_id: int, expected_revision: int, actor: str) -> None:
    with session_factory(engine).begin() as s:
        who = s.get(Account, actor)
        if who is None or who.role not in ("admin", "planner") or not who.active:
            raise ValueError("Geen rechten om een planning te publiceren.")
        w = s.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
        row = s.get(PlanningVersion, plan_id)
        if row is None or w is None or w.revision != expected_revision or row.workspace_revision != expected_revision:
            raise ConflictError("Deze planning is verouderd. Bereken opnieuw met de actuele invoergegevens.")
        if row.payload.get("status") not in ("OPTIMAL", "FEASIBLE"):
            raise ValueError("Er is geen geldige planning om te publiceren.")
        row.published_at = now()
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
        w = s.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
        if w is None or not any(e["id"] == employee_id and e.get("active", True)
                                for e in w.payload["employees"]):
            raise ValueError("Dit account is niet aan een actieve controleur gekoppeld.")
        dates = leave_days(start, end, int(w.payload["year"]), int(w.payload["month"]))
        for other in s.scalars(select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status.in_(("pending", "approved")))).all():
            if start <= other.end_date and other.start_date <= end:
                raise ValueError("Er bestaat al een openstaande of goedgekeurde aanvraag voor deze dagen.")
        existing = {(c["employee_id"], c["date"]) for c in w.payload.get("hour_credits", [])}
        if any((employee_id, day.isoformat()) in existing for day in dates):
            raise ValueError("Op één of meer aangevraagde dagen staat al een geregistreerde afwezigheid.")
        row = LeaveRequest(employee_id=employee_id, start_date=start, end_date=end,
                           status="pending", created_at=now())
        s.add(row)
        s.flush()
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
        return [_leave_dict(r) for r in s.scalars(query).all()]


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
        w = s.scalar(select(Workspace).where(Workspace.id == 1).with_for_update())
        row = s.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update())
        if not row or row.status != "pending":
            raise ValueError("Deze aanvraag is niet meer in behandeling.")
        if w is None:
            raise ValueError("Werkruimte ontbreekt.")
        days = leave_days(row.start_date, row.end_date,
                          int(w.payload["year"]), int(w.payload["month"]))
        if approve:
            if not isinstance(hours_per_day, (int, float)) or not 0 <= hours_per_day <= 16:
                raise ValueError("Testuren moeten tussen 0 en 16 liggen.")
            if not any(e["id"] == row.employee_id and e.get("active", True)
                       for e in w.payload["employees"]):
                raise ValueError("Controleur bestaat niet meer of is niet actief.")
            payload = dict(w.payload)
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
        _audit(s, actor, f"Verlofaanvraag #{row.id} {row.status} door {actor}")
        return {"id": row.id, "status": row.status, "workspace_revision": w.revision}
