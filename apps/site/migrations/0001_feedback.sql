-- Corrections and requests sent from the site's "فيه حاجة غلط؟" form.
-- No IP addresses or other identifiers are stored; `contact` is optional and only
-- present when the sender chose to leave a phone number or email for a reply.
CREATE TABLE feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  page TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT,
  contact TEXT,
  status TEXT NOT NULL DEFAULT 'new'
);
