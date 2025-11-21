# Pet Grooming by Sofia (Intentionally Vulnerable)

This tiny Node/Express + SQLite stack is purpose-built as a hackathon sandbox. It is **not** secure. Everything here is wired the wrong way on purpose so red-team style agents can poke holes while blue-team agents observe.

## Features

- Plaintext password storage, string-concatenated SQL queries, and missing session enforcement.
- Exposed admin panel with downloadable database paths and zero authentication.
- Debug + env + source dumping routes that leak server internals and API keys.
- Honey-pot JSON endpoints (`/admin-v2`, `/backup-db`, `/config-prod`) for monitoring.
- Static frontend asset that leaks an analytics key (`public/js/app.js`).
- Every HTTP request is mirrored into `attack_log.json` for replay/analysis.

## Running locally

```bash
npm install
npm start
```

The server listens on `http://localhost:3000` by default.

## Intentional vulnerabilities

| Area | Intentional issue |
| --- | --- |
| Auth | No sessions, weak login, plaintext passwords |
| Database | SQLite file exposed, SQL injection by concatenation |
| Files | `/download-db` + `/source` accept path traversal |
| Secrets | Hardcoded keys and `/env` dump |
| Debug | `/debug` and `/env` leak everything |
| Logging | `attack_log.json` captures bodies (PII) |

Do **not** deploy this application to production. It exists solely as a training target.
