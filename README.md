# Post-Bid Tracker

Interactive web-based checklist for tracking bid submissions and follow-ups with General Contractors.

## Features

- Track multiple GCs per bid submission
- Automated follow-up scheduling (Day 2, 7, 14, 28)
- Visual status tracking (Active, Won, Lost, No Response)
- Local storage persistence (saves per bid number)
- Export summaries to text files
- Collapsible GC entries for managing large bid lists

## Usage

1. Open `bid_tracker.html` in any modern web browser
2. Enter bid number and project name
3. Complete pre-submission and submission tasks
4. Add GC entries for each general contractor
5. Track follow-ups and responses for each GC
6. Mark outcomes and complete close actions

## Files

| File | Description |
|------|-------------|
| `index.html` | Interactive web-based tracker (main application) |
| `post_bid_checklist_v2.md` | Printable markdown checklist template |
| `post_bid_tracking_v2.py` | Python automation scripts |
| `post_bid_tracking_docs.md` | Documentation and workflow guides |

## Data Storage

Data is stored in your browser's localStorage, keyed by bid number. To access data across devices or share with team members, use the Export function and share the generated summary files.

## Browser Compatibility

Works in all modern browsers (Chrome, Firefox, Edge, Safari). No server required - runs entirely in the browser.
