"""Datalaag voor de v0.2-proefversie (PostgreSQL of lokale SQLite-test).

Geen echte personeelsgegevens gebruiken op gratis Community Cloud zonder goedkeuring.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.exc import IntegrityError

from demo_data import build_demo


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
