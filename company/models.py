"""SQLAlchemy models for all five Meridian Freight systems."""

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# HR System
# ---------------------------------------------------------------------------

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # individual_contributor, manager, hr_partner, finance_analyst, sales_rep, executive, contractor
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    groups: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    department: Mapped["Department"] = relationship(back_populates="employees")
    manager: Mapped["Employee | None"] = relationship(remote_side="Employee.id")
    salary_records: Mapped[list["Salary"]] = relationship(back_populates="employee")
    performance_reviews: Mapped[list["PerformanceReview"]] = relationship(
        back_populates="employee",
        foreign_keys="[PerformanceReview.employee_id]",
    )
    leave_records: Mapped[list["LeaveRecord"]] = relationship(back_populates="employee")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Salary(Base):
    __tablename__ = "salaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="salary_records")


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    employee: Mapped["Employee"] = relationship(
        back_populates="performance_reviews", foreign_keys=[employee_id]
    )
    reviewer: Mapped["Employee"] = relationship(foreign_keys=[reviewer_id])


class LeaveRecord(Base):
    __tablename__ = "leave_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    leave_type: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # approved, pending, denied
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="leave_records")


class TerminationRecord(Base):
    __tablename__ = "termination_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pending, completed
    initiated_by: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])
    initiator: Mapped["Employee"] = relationship(foreign_keys=[initiated_by])


# ---------------------------------------------------------------------------
# Ticketing System
# ---------------------------------------------------------------------------

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # open, in_progress, resolved, closed
    priority: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high, critical
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # it, ops, hr_complaint, security_incident
    owner_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    team: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    owner: Mapped["Employee"] = relationship(foreign_keys=[owner_id])
    assignee: Mapped["Employee | None"] = relationship(foreign_keys=[assignee_id])
    comments: Mapped[list["TicketComment"]] = relationship(back_populates="ticket")


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    ticket: Mapped["Ticket"] = relationship(back_populates="comments")
    author: Mapped["Employee"] = relationship()


# ---------------------------------------------------------------------------
# Document Store
# ---------------------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # policy, contract, wiki, board_minutes
    owner_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    access_groups: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    owner: Mapped["Employee"] = relationship()
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True)
    access_groups: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# Team Chat
# ---------------------------------------------------------------------------

class ChatChannel(Base):
    __tablename__ = "chat_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    members: Mapped[list["ChannelMember"]] = relationship(back_populates="channel")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="channel")


class ChannelMember(Base):
    __tablename__ = "channel_members"
    __table_args__ = (UniqueConstraint("channel_id", "employee_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("chat_channels.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)

    channel: Mapped["ChatChannel"] = relationship(back_populates="members")
    employee: Mapped["Employee"] = relationship()


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("chat_channels.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    channel: Mapped["ChatChannel"] = relationship(back_populates="messages")
    author: Mapped["Employee"] = relationship()


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    stage: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # prospecting, qualification, proposal, negotiation, closed_won, closed_lost
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    canary: Mapped[str | None] = mapped_column(String(100), nullable=True)

    customer: Mapped["Customer"] = relationship()
    owner: Mapped["Employee"] = relationship()


# ---------------------------------------------------------------------------
# Canary Registry
# ---------------------------------------------------------------------------

class CanaryRecord(Base):
    __tablename__ = "canary_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canary: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # salary, review, termination, ticket, document, message, deal
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    required_permission: Mapped[str] = mapped_column(String(200), nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    allowed_employee_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(20), nullable=False)  # allow, deny
    result_status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, error, denied
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
