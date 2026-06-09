# Security & Single Sign-On (SSO)

## Single Sign-On
SSO via SAML 2.0 and Google Workspace is available on the Enterprise plan. Admins
configure SSO under **Settings → Security → SSO**. Once enforced, members sign in through
your identity provider and local passwords are disabled.

## Session management
Active sessions are listed under **Settings → Security → Sessions**. You can revoke any
session remotely. Sessions expire after 30 days of inactivity.

## Data protection
Nimbus encrypts data in transit (TLS 1.2+) and at rest (AES-256). Audit logs of admin
actions are available to Enterprise workspaces under **Settings → Security → Audit log**.
