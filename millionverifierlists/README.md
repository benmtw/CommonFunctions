# Million Verifier Lists

This directory contains email verification result files from two providers.

## Sources

### 1. MillionVerifier

- **API**: https://developer.millionverifier.com/#operation/bulk-download
- **How to identify**: Filenames contain `MILLIONVERIFIER` (e.g. `_FULL_REPORT_MILLIONVERIFIER.COM.csv` or `_FILTERED_MILLIONVERIFIER.COM.csv`)

#### CSV Columns

| Column | Description |
|--------|-------------|
| `email` | The email address that was verified |
| `quality` | Overall quality rating: `good`, `risky`, or `bad` |
| `result` | Specific result code (see below) |
| `free` | Whether the email is from a free provider (e.g. Gmail, Hotmail, Yahoo) — `yes` or `no` |
| `role` | Whether the email is a role-based address (e.g. sales@, admin@, support@) rather than a person — `yes` or `no` |

If the original uploaded file contained additional columns, those are preserved in the output.

#### Result Values

| Quality | Result | Meaning |
|---------|--------|---------|
| **good** | `ok` | Email exists and is safe to send to |
| **risky** | `catch_all` | The mail server accepts all emails regardless of whether the address exists |
| **risky** | `unknown` | Could not determine whether the email exists |
| **bad** | `invalid` | Email address does not exist |
| **bad** | `disposable` | Email is hosted on a temporary/disposable email provider |

#### Report Types

- **FULL_REPORT** — contains all verified emails with all result types
- **FILTERED** — contains only a subset of results (e.g. good only, bad only, or a custom filter)

---

### 2. EmailListVerify

- **API**: https://api.emaillistverify.com/api-doc
- **How to identify**: CSV files with columns `Email`, `result`, `EmailDomain` (no `MILLIONVERIFIER` in filename)

#### CSV Columns

| Column | Description |
|--------|-------------|
| `Email` | The email address that was verified |
| `result` | Verification result code (see below) |
| `EmailDomain` | The domain part of the email address |

#### Result Values

| Result | Meaning |
|--------|---------|
| `ok` | Email is valid and exists |
| `invalid` | Email address does not exist |
| `invalid_mx` | Domain has no valid MX (mail server) records |
| `accept_all` | Mail server accepts all emails (catch-all); deliverability uncertain |
| `ok_for_all` | Server responds OK for all addresses; individual existence unverifiable |
| `disposable` | Temporary/disposable email address |
| `role` | Role-based address (e.g. info@, admin@) not tied to a specific person |
| `email_disabled` | Email account exists but has been disabled |
| `dead_server` | Mail server is not responding |
| `unknown` | Verification could not be completed |
