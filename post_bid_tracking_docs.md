# Post-Bid Tracking System — Documentation

## What Changed from Original

### Bugs Fixed
1. **Follow-up progression was broken** — Original only set first touchpoint, never advanced
2. **No way to mark follow-ups as sent** — Critical gap for execution tracking
3. **No receipt confirmation trigger** — Status existed but no function to set it
4. **Missing GC email templates** — Only had Sean emails, not the actual follow-ups
5. **No action queries** — Couldn't answer "what's due today?"
6. **State transitions lacked validation** — Could move to invalid states

### Optimizations Added
1. **Follow-up state machine** — Each touchpoint tracked individually with completion status
2. **Query methods on PostBidRecord** — `.next_followup`, `.overdue_followups`, `.is_blocked`, etc.
3. **Action query functions** — `get_followups_due_today()`, `get_bids_awaiting_sean()`, etc.
4. **GC email generators** — All 4 follow-up templates (receipt/status/value/closeout)
5. **Daily action report** — Single function shows everything that needs attention
6. **Better close tracking** — Separate functions for won/lost/no-response with proper metadata
7. **Audit logging** — Every state change logged with timestamp

---

## Core Concepts

### The Two-State Rule (Pre-Submission)
If a bid is NOT submitted, it must be in exactly one of these states:
- `AWAITING_SEAN_INPUT` — Blocked on a specific question
- `READY_TO_SUBMIT` — Unblocked, can submit right now

**No gray zone.** This prevents "did it get done?" confusion.

### Post-Submission State Machine
```
SUBMITTED → RECEIPT_CONFIRMED → FOLLOWUP_ACTIVE → GC_RESPONSE_LOGGED → CLOSED_*
                     ↓                                        ↓
              (optional step)                          (repeatable)
```

### Follow-Up Schedule (Automatic)
When you call `mark_submitted()`, it automatically creates 4 follow-up records:
- Day 2: Receipt confirmation
- Day 7: Status check
- Day 14: Value touch
- Day 28: Closeout request

Each has:
- `scheduled_dt` — When it should be sent
- `sent_dt` — When it was actually sent (None until you mark it)
- `gc_responded` — Did GC respond to this touchpoint?
- `response_note` — What they said

---

## Key Functions

### Pre-Submission
```python
mark_awaiting_sean(bid, question="Choose Low/Mid/High", deadline=due_dt)
# Blocks bid, generates Sean email

mark_ready_to_submit(bid, note="Sean approved Mid lane")
# Unblocks bid
```

### Submission
```python
mark_submitted(bid, submission_dt=now, proof_ref="screenshot.png")
# - Sets submission timestamp
# - Saves proof reference
# - Creates 4 follow-up records automatically
# - Transitions to FOLLOWUP_ACTIVE
```

### Follow-Ups
```python
# Mark as sent
mark_followup_sent(bid, FollowUpType.RECEIPT_CONFIRMATION)

# Generate email
email = generate_followup_email(bid, FollowUpType.STATUS_CHECK)
# Returns Email(subject=..., body=..., to=...)
```

### GC Responses
```python
record_gc_response(
    bid,
    GCResponseType.REVIEWING,
    "GC said they're reviewing bids this week"
)
# Logs response, marks current follow-up as responded
```

### Closing
```python
# Won
close_bid_won(bid, award_amount=150000.0, note="Final scope clarified")

# Lost
close_bid_lost(
    bid,
    reason=LossReason.PRICE,
    winning_sub="Competitor Co",
    winning_price=125000.0,
    note="Lost by $5k"
)

# No response
close_bid_no_response(bid, note="28 days, zero response")
```

---

## Action Queries (What needs to be done?)

### Daily Workflow
```python
# Start each day with this
print_daily_action_report(all_bids)
# Shows:
# - Bids awaiting Sean input (with deadlines)
# - Bids ready to submit
# - Overdue follow-ups
# - Follow-ups due today
# - Bids that need to be closed
```

### Individual Queries
```python
# Get specific action items
blocked = get_bids_awaiting_sean(bids)
ready = get_bids_ready_to_submit(bids)
overdue = get_overdue_followups(bids)
due_today = get_followups_due_today(bids)
needs_close = get_bids_needing_close(bids, days_threshold=30)
```

### Bid-Level Queries
```python
# On individual bid
next_action = bid.next_followup  # Returns next incomplete FollowUpRecord
overdue = bid.overdue_followups  # List of overdue follow-ups
days_old = bid.days_since_submission  # Int or None

# Booleans
if bid.is_blocked:  # Awaiting Sean?
if bid.is_submitted:  # Has submission_dt?
if bid.is_closed:  # In a CLOSED_* state?
```

---

## Email Generation

### To Sean (2 templates)
```python
# When blocked
email = email_to_sean_awaiting_input(bid)

# When submitted
email = email_to_sean_submitted(bid)
```

### To GC (4 templates)
```python
# Manual (specify type)
email = generate_followup_email(bid, FollowUpType.RECEIPT_CONFIRMATION)

# Or direct
email = email_to_gc_receipt_confirmation(bid)
email = email_to_gc_status_check(bid)
email = email_to_gc_value_touch(bid)
email = email_to_gc_closeout_request(bid)
```

All return `Email(subject, body, to)` dataclass.

---

## Typical Workflow

### 1. Create bid record
```python
bid = PostBidRecord(
    bid_id="736",
    project_name="Retail Shell",
    gc_company="BuildFast GC",
    estimator_name="Jane Doe",
    estimator_email="jane@buildfast.com",
    platform="PlanHub",
    due_dt=datetime(2026, 1, 20, 14, 0)
)
```

### 2. If blocked, get Sean's input
```python
mark_awaiting_sean(bid, "Choose Low/Mid/High lane (recommend Mid)", bid.due_dt)
email = email_to_sean_awaiting_input(bid)
# Send email, wait for response
```

### 3. When unblocked, submit
```python
mark_ready_to_submit(bid, "Sean approved Mid")
mark_submitted(bid, datetime.now(), proof_ref="planhub_confirmation.png")
email = email_to_sean_submitted(bid)
# Send confirmation to Sean
```

### 4. Run daily actions
```python
# Each morning
print_daily_action_report(all_bids)

# Send any due follow-ups
for bid, followup in get_followups_due_today(all_bids):
    email = generate_followup_email(bid, followup.followup_type)
    # Send email
    mark_followup_sent(bid, followup.followup_type)
```

### 5. Log GC responses
```python
record_gc_response(bid, GCResponseType.NEED_REVISION, "GC wants pricing without X")
```

### 6. Close when done
```python
# If you won
close_bid_won(bid, award_amount=135000.0)

# If you lost
close_bid_lost(bid, LossReason.PRICE, winning_sub="Competitor", winning_price=120000.0)

# If they ghosted
close_bid_no_response(bid)
```

---

## Data Structure Reference

### PostBidRecord (main object)
```python
@dataclass
class PostBidRecord:
    # Identity
    bid_id: str
    project_name: str
    gc_company: str
    estimator_name: str
    estimator_email: str
    estimator_phone: Optional[str]
    platform: str  # PlanHub/ConstructConnect/Email
    
    # Timeline
    due_dt: Optional[datetime]
    submission_dt: Optional[datetime]
    
    # State
    status: PostBidStatus
    
    # Submission proof
    submission_proof_ref: Optional[str]
    
    # Sean blocking
    awaiting_sean_question: Optional[str]
    awaiting_sean_deadline: Optional[datetime]
    
    # Follow-ups
    followups: List[FollowUpRecord]  # Auto-created on submission
    
    # GC responses
    last_gc_response: Optional[GCResponseType]
    gc_response_notes: List[str]
    
    # Close data
    close_dt: Optional[datetime]
    loss_reason: Optional[LossReason]
    winning_sub: Optional[str]
    winning_price: Optional[float]
    award_amount: Optional[float]
    close_notes: Optional[str]
    
    # Audit
    logs: List[PostBidLog]
```

### FollowUpRecord
```python
@dataclass
class FollowUpRecord:
    followup_type: FollowUpType  # RECEIPT_CONFIRMATION, STATUS_CHECK, etc.
    scheduled_dt: datetime  # When it should be sent
    sent_dt: Optional[datetime]  # When it was actually sent
    gc_responded: bool  # Did GC respond to this?
    response_note: Optional[str]  # What they said
    
    @property
    def is_overdue(self) -> bool  # Past scheduled_dt, not sent
    
    @property
    def is_complete(self) -> bool  # Has sent_dt
```

---

## Integration Points

### Database Persistence
Convert to/from dict for storage:
```python
# Save
bid_dict = {
    "bid_id": bid.bid_id,
    "project_name": bid.project_name,
    # ... all fields
    "followups": [
        {
            "followup_type": f.followup_type.value,
            "scheduled_dt": f.scheduled_dt.isoformat(),
            "sent_dt": f.sent_dt.isoformat() if f.sent_dt else None,
            # ...
        }
        for f in bid.followups
    ],
    "logs": [
        {
            "ts": log.ts.isoformat(),
            "status": log.status.value,
            "note": log.note,
        }
        for log in bid.logs
    ]
}

# Load
bid = PostBidRecord(
    bid_id=data["bid_id"],
    # ... reconstruct from dict
)
```

### Scheduled Jobs
```python
# Daily cron job
def daily_followup_job():
    bids = load_all_active_bids()
    
    # Send due follow-ups
    for bid, followup in get_followups_due_today(bids):
        email = generate_followup_email(bid, followup.followup_type)
        send_email(email)
        mark_followup_sent(bid, followup.followup_type)
        save_bid(bid)
    
    # Alert on overdue
    overdue = get_overdue_followups(bids)
    if overdue:
        send_alert(f"{len(overdue)} overdue follow-ups")
```

### UI Dashboard
```python
# Show metrics
active_bids = [b for b in bids if not b.is_closed]
blocked_count = len(get_bids_awaiting_sean(bids))
overdue_count = len(get_overdue_followups(bids))
due_today_count = len(get_followups_due_today(bids))

# Show bid details
print_bid_summary(selected_bid)
```

---

## Hard Rules

1. **Pre-submission**: Bid must be `AWAITING_SEAN_INPUT` or `READY_TO_SUBMIT`. No gray zone.

2. **Sean emails**: Only send these automatically:
   - `AWAITING_SEAN_INPUT` → Send blocking email
   - `SUBMITTED` → Send confirmation email

3. **Follow-up schedule**: Created automatically on submission. Don't manually create follow-ups.

4. **State transitions**: Use provided functions. They validate and log properly.

5. **Close completeness**: When closing, always provide:
   - Won: `award_amount`
   - Lost: `loss_reason`, optionally `winning_sub` and `winning_price`
   - No response: optional `note`

6. **Follow-up marking**: Mark as sent AFTER actually sending, not before.

---

## Testing

Run the example:
```bash
python post_bid_tracking_v2.py
```

Shows:
- Blocking Sean for input
- Submitting bid
- Sending follow-ups
- Recording GC response
- Closing as lost
- Daily action report

---

## Next Steps for Production

1. **Persistence layer** — Add database save/load functions
2. **Email integration** — Connect to SMTP or email API
3. **Scheduled jobs** — Set up daily cron for follow-ups
4. **UI/Dashboard** — Build interface around action queries
5. **Notification system** — Alert on overdue items
6. **Analytics** — Win/loss reporting from close data
7. **Multi-user** — Add user assignment if needed
8. **Audit export** — Generate reports from logs

The core state machine is solid. Build your infrastructure around these functions.
