# Troubleshooting Common Issues

## Resetting your password
Click **Forgot password** on the login page and enter your account email. You will
receive a reset link valid for 60 minutes. If the email does not arrive, check your spam
folder and confirm you are using the address you signed up with.

## Two-factor authentication (2FA)
Enable 2FA under **Settings → Security**. Scan the QR code with an authenticator app
(Google Authenticator, 1Password, Authy). Store your backup codes safely — if you lose
your device, a backup code is the only way to sign in without contacting support.

## "500 Internal Server Error" on export
A 500 error when exporting usually means the export exceeded the size limit. Exports are
capped at 100,000 rows on the Starter plan and 1,000,000 rows on Pro. Narrow your date
range or filter the dataset, then retry. If the error persists on a small export, it is a
service issue — check status.nimbus.example.

## Dashboards not loading
Hard-refresh the page (Cmd/Ctrl+Shift+R). If a dashboard still fails to load, it may
reference a deleted data source; open it in edit mode to reconnect the source.
