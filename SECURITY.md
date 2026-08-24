# Security policy

Do not disclose a vulnerability publicly before maintainers have had a reasonable opportunity to patch it. Until a public security contact is established, report privately to the repository owner after publication.

Relevant vulnerability classes include:

- loading a `VOICE.md` from an untrusted source;
- remote inheritance without integrity controls;
- escaping the communication-only authority boundary;
- installer overwrites of unmanaged files;
- sidecar exposure beyond localhost without authentication;
- prompt or secret leakage in logs;
- path traversal through adapters or inheritance.

The draft package intentionally disables remote `extends`, binds the sidecar to localhost by default, and uses managed installer markers.
