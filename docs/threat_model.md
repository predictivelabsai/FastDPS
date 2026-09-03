# FastDPS threat model

## Protected assets

- Procurement plans, supplier evidence, submissions, scores, decisions, and
  contracts.
- Organisation memberships, roles, permissions, invitations, and sessions.
- Uploaded documents and identity-provider or model-provider credentials.
- The integrity and completeness of the audit trail.

## Principal threats and controls

| Threat | Control |
| --- | --- |
| Cross-organisation record access | Actor context from a validated membership; organisation predicates on business queries; tenant-isolation tests. |
| Privilege escalation | Fixed permission catalogue; dynamic roles can only contain known keys; non-platform users cannot grant rights they do not hold. |
| Owner lockout | The protected owner role retains administration rights and the last owner cannot lose it. |
| Chat performs an unintended action | Read/write tool separation, structured preview, expiring confirmation, atomic claim, live permission recheck, and audit event. |
| CSRF on browser mutations | SameSite session cookie plus per-session token required by forms and API writes. |
| Password disclosure | PBKDF2-SHA256 with a random salt and 600,000 iterations; no plaintext or default production passwords. |
| OAuth account substitution | Random state, constant-time comparison, verified ID token and email, optional domain/email allowlists. |
| Malicious file path | Basename normalization, generated tenant/document directories, resolved-path containment check, and content hash. |
| Duplicate import or webhook | File and release checksums, unique keys, and webhook receipt records. |
| SQL injection | Parameterized values and validated PostgreSQL schema identifiers. |
| Model prompt injection | Model output is explanatory text only; it has no SQL or execution authority. Tool actions are locally parsed and policy checked. |

## Deployment responsibilities

Operators must set a strong `FASTDPS_SECRET`, terminate TLS, limit database and
filesystem privileges, encrypt backups and persistent volumes, rotate provider
credentials, configure retention, scan uploads for malware, and monitor failed
authentication and authorization events. The local test-auth route must remain
disabled outside an isolated demonstration environment.
