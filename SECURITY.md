# Security policy

Do not disclose a vulnerability publicly before maintainers have had a reasonable opportunity to patch it.

Report privately to `forcewake@gmail.com` with the subject prefix `[VoiceMD security]`. Include the affected version or commit, reproduction steps, impact, and any suggested mitigation. Do not include live credentials, production data, or unrelated personal data. If email is not suitable for the evidence, send an initial description and arrange a safer transfer channel before attaching sensitive material.

The maintainer should acknowledge a report within seven calendar days and coordinate disclosure after a fix or documented risk decision. If no acknowledgement arrives, the reporter may follow a coordinated-disclosure policy appropriate to the impact.

Relevant vulnerability classes include:

- loading a `VOICE.md` from an untrusted source;
- remote inheritance without integrity controls;
- escaping the communication-only authority boundary;
- installer overwrites of unmanaged files;
- sidecar exposure beyond localhost without authentication;
- prompt or secret leakage in logs;
- path traversal through adapters or inheritance.

The draft package intentionally disables remote `extends`, binds the sidecar to localhost by default, and uses managed installer markers.
