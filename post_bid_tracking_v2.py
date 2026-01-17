"""
Post-Bid Tracking System
Starts at submission, tracks through close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class PostBidStatus(str, Enum):
    """Post-submission lifecycle states."""
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    AWAITING_SEAN_INPUT = "AWAITING_SEAN_INPUT"
    SUBMITTED = "SUBMITTED"
    RECEIPT_CONFIRMED = "RECEIPT_CONFIRMED"
    FOLLOWUP_ACTIVE = "FOLLOWUP_ACTIVE"
    GC_RESPONSE_LOGGED = "GC_RESPONSE_LOGGED"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"
    CLOSED_NO_RESPONSE = "CLOSED_NO_RESPONSE"

    @property
    def is_closed(self) -> bool:
        return self in (
            PostBidStatus.CLOSED_WON,
            PostBidStatus.CLOSED_LOST,
            PostBidStatus.CLOSED_NO_RESPONSE,
        )


class FollowUpType(str, Enum):
    """Follow-up touchpoint types."""
    RECEIPT_CONFIRMATION = "RECEIPT_CONFIRMATION"  # Day 2
    STATUS_CHECK = "STATUS_CHECK"  # Day 7
    VALUE_TOUCH = "VALUE_TOUCH"  # Day 14
    CLOSEOUT_REQUEST = "CLOSEOUT_REQUEST"  # Day 28


class GCResponseType(str, Enum):
    """GC response categories."""
    REVIEWING = "REVIEWING"
    AWARDED = "AWARDED"
    NEED_REVISION = "NEED_REVISION"
    SCOPE_CLARIFICATION = "SCOPE_CLARIFICATION"
    INVITE_TO_SUBMIT = "INVITE_TO_SUBMIT"
    NO_RESPONSE = "NO_RESPONSE"
    UNKNOWN = "UNKNOWN"


class LossReason(str, Enum):
    """Why we lost the bid."""
    PRICE = "PRICE"
    SCOPE = "SCOPE"
    SCHEDULE = "SCHEDULE"
    RELATIONSHIP = "RELATIONSHIP"
    UNKNOWN = "UNKNOWN"


# Follow-up schedule: (Type, Days after submission)
FOLLOWUP_SCHEDULE = [
    (FollowUpType.RECEIPT_CONFIRMATION, 2),
    (FollowUpType.STATUS_CHECK, 7),
    (FollowUpType.VALUE_TOUCH, 14),
    (FollowUpType.CLOSEOUT_REQUEST, 28),
]


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class PostBidLog:
    """Audit log entry."""
    ts: datetime
    status: PostBidStatus
    note: str


@dataclass
class FollowUpRecord:
    """Individual follow-up touchpoint tracking."""
    followup_type: FollowUpType
    scheduled_dt: datetime
    sent_dt: Optional[datetime] = None
    gc_responded: bool = False
    response_note: Optional[str] = None

    @property
    def is_overdue(self) -> bool:
        return self.sent_dt is None and datetime.now() > self.scheduled_dt

    @property
    def is_complete(self) -> bool:
        return self.sent_dt is not None


@dataclass
class PostBidRecord:
    """Complete post-submission bid tracking record."""
    
    # Identity
    bid_id: str
    project_name: str
    gc_company: str
    estimator_name: str
    estimator_email: str
    estimator_phone: Optional[str] = None
    platform: str = "Email"  # PlanHub/ConstructConnect/Email
    
    # Timeline
    due_dt: Optional[datetime] = None
    submission_dt: Optional[datetime] = None
    
    # State
    status: PostBidStatus = PostBidStatus.READY_TO_SUBMIT
    
    # Submission proof
    submission_proof_ref: Optional[str] = None  # filepath/screenshot/confirmation
    
    # Sean input blocking
    awaiting_sean_question: Optional[str] = None
    awaiting_sean_deadline: Optional[datetime] = None
    
    # Follow-ups
    followups: List[FollowUpRecord] = field(default_factory=list)
    
    # GC responses
    last_gc_response: Optional[GCResponseType] = None
    gc_response_notes: List[str] = field(default_factory=list)
    
    # Close data
    close_dt: Optional[datetime] = None
    loss_reason: Optional[LossReason] = None
    winning_sub: Optional[str] = None
    winning_price: Optional[float] = None
    award_amount: Optional[float] = None
    close_notes: Optional[str] = None
    
    # Audit log
    logs: List[PostBidLog] = field(default_factory=list)
    
    # Metadata
    created_dt: datetime = field(default_factory=datetime.now)
    
    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------
    
    @property
    def is_submitted(self) -> bool:
        """Has this bid been submitted?"""
        return self.submission_dt is not None
    
    @property
    def is_closed(self) -> bool:
        """Is this bid in a closed state?"""
        return self.status.is_closed
    
    @property
    def is_blocked(self) -> bool:
        """Is this bid awaiting Sean input?"""
        return self.status == PostBidStatus.AWAITING_SEAN_INPUT
    
    @property
    def next_followup(self) -> Optional[FollowUpRecord]:
        """Get the next incomplete follow-up."""
        incomplete = [f for f in self.followups if not f.is_complete]
        return incomplete[0] if incomplete else None
    
    @property
    def overdue_followups(self) -> List[FollowUpRecord]:
        """Get all overdue follow-ups."""
        return [f for f in self.followups if f.is_overdue]
    
    @property
    def days_since_submission(self) -> Optional[int]:
        """Days since submission."""
        if not self.submission_dt:
            return None
        return (datetime.now() - self.submission_dt).days
    
    def get_followup_by_type(self, followup_type: FollowUpType) -> Optional[FollowUpRecord]:
        """Get a specific follow-up by type."""
        matches = [f for f in self.followups if f.followup_type == followup_type]
        return matches[0] if matches else None


# ============================================================================
# STATE TRANSITIONS
# ============================================================================

def log_status(bid: PostBidRecord, status: PostBidStatus, note: str) -> None:
    """Log a status change."""
    bid.status = status
    bid.logs.append(PostBidLog(ts=datetime.now(), status=status, note=note))


def mark_awaiting_sean(
    bid: PostBidRecord,
    question: str,
    deadline: Optional[datetime] = None
) -> None:
    """
    Mark bid as blocked awaiting Sean's input.
    
    This is the only valid "not submitted" state besides READY_TO_SUBMIT.
    """
    if bid.is_submitted:
        raise ValueError("Cannot mark as awaiting Sean after submission.")
    
    bid.awaiting_sean_question = question
    bid.awaiting_sean_deadline = deadline
    log_status(
        bid,
        PostBidStatus.AWAITING_SEAN_INPUT,
        f"Blocked: {question}"
    )


def mark_ready_to_submit(bid: PostBidRecord, note: str = "Ready to submit") -> None:
    """Mark bid as ready to submit (unblocked)."""
    if bid.is_submitted:
        raise ValueError("Cannot mark as ready to submit after submission.")
    
    bid.awaiting_sean_question = None
    bid.awaiting_sean_deadline = None
    log_status(bid, PostBidStatus.READY_TO_SUBMIT, note)


def mark_submitted(
    bid: PostBidRecord,
    submission_dt: datetime,
    proof_ref: str
) -> None:
    """
    Mark bid as submitted and initialize follow-up schedule.
    
    This is the critical transition that starts the follow-up machine.
    """
    if bid.is_submitted:
        raise ValueError("Bid already submitted.")
    
    bid.submission_dt = submission_dt
    bid.submission_proof_ref = proof_ref
    bid.awaiting_sean_question = None
    bid.awaiting_sean_deadline = None
    
    # Initialize follow-up schedule
    for followup_type, days_offset in FOLLOWUP_SCHEDULE:
        scheduled_dt = submission_dt + timedelta(days=days_offset)
        bid.followups.append(
            FollowUpRecord(
                followup_type=followup_type,
                scheduled_dt=scheduled_dt
            )
        )
    
    log_status(bid, PostBidStatus.SUBMITTED, f"Submitted with proof: {proof_ref}")
    log_status(
        bid,
        PostBidStatus.FOLLOWUP_ACTIVE,
        f"Follow-up schedule initialized ({len(bid.followups)} touchpoints)"
    )


def mark_receipt_confirmed(bid: PostBidRecord, note: str = "GC confirmed receipt") -> None:
    """Mark that GC confirmed receipt."""
    if not bid.is_submitted:
        raise ValueError("Cannot confirm receipt before submission.")
    
    log_status(bid, PostBidStatus.RECEIPT_CONFIRMED, note)


def mark_followup_sent(
    bid: PostBidRecord,
    followup_type: FollowUpType,
    sent_dt: Optional[datetime] = None
) -> None:
    """
    Mark a follow-up as sent.
    
    This is how you track progression through the follow-up schedule.
    """
    if not bid.is_submitted:
        raise ValueError("Cannot send follow-up before submission.")
    
    followup = bid.get_followup_by_type(followup_type)
    if not followup:
        raise ValueError(f"No follow-up found for type: {followup_type}")
    
    if followup.is_complete:
        raise ValueError(f"Follow-up {followup_type} already marked as sent.")
    
    followup.sent_dt = sent_dt or datetime.now()
    log_status(
        bid,
        PostBidStatus.FOLLOWUP_ACTIVE,
        f"Follow-up sent: {followup_type.value}"
    )


def record_gc_response(
    bid: PostBidRecord,
    response_type: GCResponseType,
    note: str
) -> None:
    """
    Record a response from the GC.
    
    This logs the response and optionally marks the current follow-up
    as having received a response.
    """
    if not bid.is_submitted:
        raise ValueError("Cannot record GC response before submission.")
    
    bid.last_gc_response = response_type
    bid.gc_response_notes.append(f"[{datetime.now().strftime('%Y-%m-%d')}] {note}")
    
    # Mark current follow-up as responded if active
    next_fu = bid.next_followup
    if next_fu and next_fu.is_complete and not next_fu.gc_responded:
        next_fu.gc_responded = True
        next_fu.response_note = note
    
    log_status(
        bid,
        PostBidStatus.GC_RESPONSE_LOGGED,
        f"{response_type.value}: {note}"
    )


def close_bid_won(
    bid: PostBidRecord,
    award_amount: float,
    note: Optional[str] = None
) -> None:
    """Close bid as WON."""
    if bid.is_closed:
        raise ValueError("Bid already closed.")
    
    bid.close_dt = datetime.now()
    bid.award_amount = award_amount
    bid.close_notes = note
    log_status(bid, PostBidStatus.CLOSED_WON, f"WON at ${award_amount:,.2f}")


def close_bid_lost(
    bid: PostBidRecord,
    reason: LossReason,
    winning_sub: Optional[str] = None,
    winning_price: Optional[float] = None,
    note: Optional[str] = None
) -> None:
    """Close bid as LOST."""
    if bid.is_closed:
        raise ValueError("Bid already closed.")
    
    bid.close_dt = datetime.now()
    bid.loss_reason = reason
    bid.winning_sub = winning_sub
    bid.winning_price = winning_price
    bid.close_notes = note
    
    reason_str = reason.value
    if winning_sub:
        reason_str += f" (lost to {winning_sub})"
    if winning_price:
        reason_str += f" at ${winning_price:,.2f}"
    
    log_status(bid, PostBidStatus.CLOSED_LOST, f"LOST: {reason_str}")


def close_bid_no_response(bid: PostBidRecord, note: Optional[str] = None) -> None:
    """Close bid due to no response from GC."""
    if bid.is_closed:
        raise ValueError("Bid already closed.")
    
    bid.close_dt = datetime.now()
    bid.close_notes = note or "GC never responded after full follow-up sequence"
    log_status(bid, PostBidStatus.CLOSED_NO_RESPONSE, bid.close_notes)


# ============================================================================
# SEAN EMAIL GENERATION
# ============================================================================

@dataclass
class Email:
    """Email message."""
    subject: str
    body: str
    to: str


def email_to_sean_awaiting_input(
    bid: PostBidRecord,
    sender_name: str = "Arron"
) -> Email:
    """Generate 'awaiting Sean input' email."""
    if not bid.awaiting_sean_question:
        raise ValueError("awaiting_sean_question is required.")
    
    deadline_str = "ASAP"
    if bid.awaiting_sean_deadline:
        deadline_str = bid.awaiting_sean_deadline.strftime("%b %d, %Y at %I:%M %p")
    
    subject = f"Bid #{bid.bid_id} NOT Submitted – Awaiting Your Input – {bid.project_name}"
    
    body = (
        f"Sean,\n\n"
        f"Bid #{bid.bid_id} – {bid.project_name} is NOT SUBMITTED yet. "
        f"I'm blocked awaiting your input:\n\n"
        f"Decision needed: {bid.awaiting_sean_question}\n"
        f"Deadline: {deadline_str}\n\n"
        f"{sender_name}\n"
    )
    
    return Email(subject=subject, body=body, to="sean@example.com")


def email_to_sean_submitted(
    bid: PostBidRecord,
    sender_name: str = "Arron"
) -> Email:
    """Generate 'bid submitted' confirmation email."""
    if not bid.submission_dt:
        raise ValueError("submission_dt is required for submitted email.")
    
    submitted_str = bid.submission_dt.strftime("%b %d, %Y at %I:%M %p")
    
    subject = f"Bid #{bid.bid_id} Submitted – {bid.project_name}"
    
    body = (
        f"Sean,\n\n"
        f"Bid #{bid.bid_id} – {bid.project_name} has been SUBMITTED.\n\n"
        f"- Submitted: {submitted_str}\n"
        f"- Platform: {bid.platform}\n"
        f"- GC/Estimator: {bid.estimator_name} / {bid.gc_company}\n"
        f"- Proof: {bid.submission_proof_ref or 'saved'}\n\n"
        f"Next step: Follow-up sequence is active (Day 2/7/14/28).\n\n"
        f"{sender_name}\n"
    )
    
    return Email(subject=subject, body=body, to="sean@example.com")


# ============================================================================
# GC FOLLOW-UP EMAIL GENERATION
# ============================================================================

def email_to_gc_receipt_confirmation(bid: PostBidRecord) -> Email:
    """Generate Day 2 receipt confirmation email to GC."""
    subject = f"Bid Confirmation – {bid.project_name} – {bid.gc_company}"
    
    body = (
        f"Hi {bid.estimator_name},\n\n"
        f"Just confirming you received our bid for {bid.project_name}.\n\n"
        f"Let me know if you need any clarifications.\n\n"
        f"Thanks,\n"
        f"Arron\n"
        f"GritForge Consultants\n"
    )
    
    return Email(subject=subject, body=body, to=bid.estimator_email)


def email_to_gc_status_check(bid: PostBidRecord) -> Email:
    """Generate Day 7 status check email to GC."""
    subject = f"Status Check – {bid.project_name}"
    
    body = (
        f"Hi {bid.estimator_name},\n\n"
        f"Checking in on the status of {bid.project_name}.\n\n"
        f"Any questions on our scope or pricing? Happy to clarify.\n\n"
        f"Thanks,\n"
        f"Arron\n"
        f"GritForge Consultants\n"
    )
    
    return Email(subject=subject, body=body, to=bid.estimator_email)


def email_to_gc_value_touch(bid: PostBidRecord) -> Email:
    """Generate Day 14 value touch email to GC."""
    subject = f"Quick Turnaround Available – {bid.project_name}"
    
    body = (
        f"Hi {bid.estimator_name},\n\n"
        f"If you need any revisions or scope adjustments on {bid.project_name}, "
        f"I can turn those around quickly.\n\n"
        f"Also happy to walk through our pricing breakdown if that would help.\n\n"
        f"Thanks,\n"
        f"Arron\n"
        f"GritForge Consultants\n"
    )
    
    return Email(subject=subject, body=body, to=bid.estimator_email)


def email_to_gc_closeout_request(bid: PostBidRecord) -> Email:
    """Generate Day 28 closeout request email to GC."""
    subject = f"Close the Loop – {bid.project_name}"
    
    body = (
        f"Hi {bid.estimator_name},\n\n"
        f"Following up one last time on {bid.project_name}.\n\n"
        f"Can you let me know the outcome? Also, would you like us on your "
        f"bid list for future projects?\n\n"
        f"Thanks,\n"
        f"Arron\n"
        f"GritForge Consultants\n"
    )
    
    return Email(subject=subject, body=body, to=bid.estimator_email)


def generate_followup_email(bid: PostBidRecord, followup_type: FollowUpType) -> Email:
    """Generate appropriate follow-up email based on type."""
    generators = {
        FollowUpType.RECEIPT_CONFIRMATION: email_to_gc_receipt_confirmation,
        FollowUpType.STATUS_CHECK: email_to_gc_status_check,
        FollowUpType.VALUE_TOUCH: email_to_gc_value_touch,
        FollowUpType.CLOSEOUT_REQUEST: email_to_gc_closeout_request,
    }
    
    generator = generators.get(followup_type)
    if not generator:
        raise ValueError(f"No email generator for {followup_type}")
    
    return generator(bid)


# ============================================================================
# ACTION QUERIES (What needs to be done today?)
# ============================================================================

def get_bids_ready_to_submit(bids: List[PostBidRecord]) -> List[PostBidRecord]:
    """Get all bids in READY_TO_SUBMIT state."""
    return [b for b in bids if b.status == PostBidStatus.READY_TO_SUBMIT]


def get_bids_awaiting_sean(bids: List[PostBidRecord]) -> List[PostBidRecord]:
    """Get all bids blocked awaiting Sean's input."""
    return [b for b in bids if b.is_blocked]


def get_overdue_followups(bids: List[PostBidRecord]) -> List[tuple[PostBidRecord, FollowUpRecord]]:
    """Get all overdue follow-ups across all bids."""
    overdue = []
    for bid in bids:
        if bid.is_closed:
            continue
        for followup in bid.overdue_followups:
            overdue.append((bid, followup))
    return overdue


def get_followups_due_today(bids: List[PostBidRecord]) -> List[tuple[PostBidRecord, FollowUpRecord]]:
    """Get all follow-ups scheduled for today."""
    today = datetime.now().date()
    due_today = []
    
    for bid in bids:
        if bid.is_closed:
            continue
        next_fu = bid.next_followup
        if next_fu and next_fu.scheduled_dt.date() == today:
            due_today.append((bid, next_fu))
    
    return due_today


def get_bids_needing_close(bids: List[PostBidRecord], days_threshold: int = 30) -> List[PostBidRecord]:
    """
    Get bids that need to be closed.
    
    Any bid >30 days old with all follow-ups sent should be closed.
    """
    needs_close = []
    for bid in bids:
        if bid.is_closed or not bid.is_submitted:
            continue
        
        # All follow-ups sent?
        all_sent = all(f.is_complete for f in bid.followups)
        
        # Old enough?
        days_old = bid.days_since_submission or 0
        
        if all_sent and days_old >= days_threshold:
            needs_close.append(bid)
    
    return needs_close


# ============================================================================
# REPORTING
# ============================================================================

def print_bid_summary(bid: PostBidRecord) -> None:
    """Print a human-readable bid summary."""
    print(f"\n{'='*70}")
    print(f"BID #{bid.bid_id}: {bid.project_name}")
    print(f"{'='*70}")
    print(f"Status: {bid.status.value}")
    print(f"GC: {bid.gc_company} / {bid.estimator_name}")
    print(f"Platform: {bid.platform}")
    
    if bid.submission_dt:
        print(f"Submitted: {bid.submission_dt.strftime('%b %d, %Y at %I:%M %p')}")
        print(f"Days since submission: {bid.days_since_submission}")
    
    if bid.is_blocked:
        print(f"\n🚫 BLOCKED: {bid.awaiting_sean_question}")
        if bid.awaiting_sean_deadline:
            print(f"   Deadline: {bid.awaiting_sean_deadline.strftime('%b %d, %Y at %I:%M %p')}")
    
    if bid.followups:
        print(f"\nFollow-ups:")
        for fu in bid.followups:
            status = "✅ SENT" if fu.is_complete else ("⏰ OVERDUE" if fu.is_overdue else "⏳ PENDING")
            scheduled = fu.scheduled_dt.strftime('%b %d')
            sent = f" (sent {fu.sent_dt.strftime('%b %d')})" if fu.sent_dt else ""
            print(f"  {status} {fu.followup_type.value:25s} scheduled {scheduled}{sent}")
    
    if bid.last_gc_response:
        print(f"\nLast GC Response: {bid.last_gc_response.value}")
    
    if bid.is_closed:
        print(f"\n{'─'*70}")
        print(f"CLOSED: {bid.status.value}")
        if bid.award_amount:
            print(f"Award: ${bid.award_amount:,.2f}")
        if bid.loss_reason:
            print(f"Reason: {bid.loss_reason.value}")
            if bid.winning_sub:
                print(f"Lost to: {bid.winning_sub}")
            if bid.winning_price:
                print(f"Winning price: ${bid.winning_price:,.2f}")
    
    print(f"{'='*70}\n")


def print_daily_action_report(bids: List[PostBidRecord]) -> None:
    """Print what needs to be done today."""
    print(f"\n{'='*70}")
    print(f"DAILY ACTION REPORT – {datetime.now().strftime('%B %d, %Y')}")
    print(f"{'='*70}\n")
    
    # Blocked bids
    blocked = get_bids_awaiting_sean(bids)
    if blocked:
        print(f"🚫 AWAITING SEAN INPUT ({len(blocked)}):")
        for bid in blocked:
            deadline = bid.awaiting_sean_deadline.strftime('%I:%M %p') if bid.awaiting_sean_deadline else "ASAP"
            print(f"  - Bid #{bid.bid_id} ({bid.project_name}): {bid.awaiting_sean_question} [by {deadline}]")
        print()
    
    # Ready to submit
    ready = get_bids_ready_to_submit(bids)
    if ready:
        print(f"✅ READY TO SUBMIT ({len(ready)}):")
        for bid in ready:
            due = bid.due_dt.strftime('%b %d at %I:%M %p') if bid.due_dt else "No deadline"
            print(f"  - Bid #{bid.bid_id} ({bid.project_name}) – Due: {due}")
        print()
    
    # Overdue follow-ups
    overdue = get_overdue_followups(bids)
    if overdue:
        print(f"⏰ OVERDUE FOLLOW-UPS ({len(overdue)}):")
        for bid, fu in overdue:
            scheduled = fu.scheduled_dt.strftime('%b %d')
            print(f"  - Bid #{bid.bid_id} ({bid.project_name}): {fu.followup_type.value} (was due {scheduled})")
        print()
    
    # Due today
    due_today = get_followups_due_today(bids)
    if due_today:
        print(f"📅 DUE TODAY ({len(due_today)}):")
        for bid, fu in due_today:
            print(f"  - Bid #{bid.bid_id} ({bid.project_name}): {fu.followup_type.value}")
        print()
    
    # Need to close
    needs_close = get_bids_needing_close(bids)
    if needs_close:
        print(f"📋 NEEDS CLOSE ({len(needs_close)}):")
        for bid in needs_close:
            print(f"  - Bid #{bid.bid_id} ({bid.project_name}) – {bid.days_since_submission} days old, all follow-ups sent")
        print()
    
    if not (blocked or ready or overdue or due_today or needs_close):
        print("✨ All clear – no actions due today.\n")
    
    print(f"{'='*70}\n")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Create a test bid
    bid = PostBidRecord(
        bid_id="736",
        project_name="Example Retail Shell",
        gc_company="Example GC",
        estimator_name="Jane Doe",
        estimator_email="jane@examplegc.com",
        platform="PlanHub",
        due_dt=datetime(2026, 1, 20, 14, 0),
    )
    
    print("\n" + "="*70)
    print("EXAMPLE 1: Bid blocked awaiting Sean input")
    print("="*70)
    
    # Block for Sean input
    mark_awaiting_sean(
        bid,
        question="Choose lane: Low / Mid / High (recommend Mid)",
        deadline=bid.due_dt
    )
    
    email = email_to_sean_awaiting_input(bid)
    print(f"\nSubject: {email.subject}")
    print(f"\n{email.body}")
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Bid submitted, follow-ups active")
    print("="*70)
    
    # Unblock and submit
    mark_ready_to_submit(bid, note="Sean approved Mid lane")
    mark_submitted(
        bid,
        submission_dt=datetime(2026, 1, 16, 10, 5),
        proof_ref="PlanHub confirmation screenshot saved"
    )
    
    email = email_to_sean_submitted(bid)
    print(f"\nSubject: {email.subject}")
    print(f"\n{email.body}")
    
    print_bid_summary(bid)
    
    print("\n" + "="*70)
    print("EXAMPLE 3: Send first follow-up")
    print("="*70)
    
    # Mark first follow-up as sent
    mark_followup_sent(bid, FollowUpType.RECEIPT_CONFIRMATION)
    
    gc_email = generate_followup_email(bid, FollowUpType.RECEIPT_CONFIRMATION)
    print(f"\nTo GC – Subject: {gc_email.subject}")
    print(f"\n{gc_email.body}")
    
    print("\n" + "="*70)
    print("EXAMPLE 4: Record GC response")
    print("="*70)
    
    record_gc_response(
        bid,
        GCResponseType.REVIEWING,
        "GC confirmed they're reviewing bids this week"
    )
    
    print_bid_summary(bid)
    
    print("\n" + "="*70)
    print("EXAMPLE 5: Close as LOST")
    print("="*70)
    
    close_bid_lost(
        bid,
        reason=LossReason.PRICE,
        winning_sub="Competitor Steel Co",
        winning_price=125000.0,
        note="Lost by $5k, GC mentioned price was main factor"
    )
    
    print_bid_summary(bid)
    
    print("\n" + "="*70)
    print("EXAMPLE 6: Daily action report")
    print("="*70)
    
    # Create a few test bids in different states
    bid2 = PostBidRecord(
        bid_id="737",
        project_name="Office Building Reno",
        gc_company="BuildRight",
        estimator_name="John Smith",
        estimator_email="john@buildright.com",
    )
    mark_awaiting_sean(bid2, "Approve custom railing exclusion", datetime.now() + timedelta(hours=2))
    
    bid3 = PostBidRecord(
        bid_id="738",
        project_name="Warehouse Expansion",
        gc_company="FastBuild",
        estimator_name="Mary Johnson",
        estimator_email="mary@fastbuild.com",
    )
    mark_ready_to_submit(bid3)
    
    all_bids = [bid, bid2, bid3]
    print_daily_action_report(all_bids)
