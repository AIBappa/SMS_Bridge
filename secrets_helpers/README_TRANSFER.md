Secrets transfer bundle for SMS Bridge

Files included:
- config.yml (cloudflared config)
- credentials-file.json (cloudflared credentials)
- vault.yml (application secrets)

Transfer instructions:
1. Copy the tarball to a secure USB or encrypted storage.
2. On the target PC, extract the tarball in a secure location, e.g. /root/.secrets_sms_bridge or another folder with strict permissions.
   Example: sudo mkdir -p /root/.secrets_sms_bridge && sudo chown $USER: /root/.secrets_sms_bridge && sudo chmod 700 /root/.secrets_sms_bridge
3. Place files where the systems expect them (examples):
   - cloudflared config: /etc/cloudflared/config.yml
   - cloudflared credentials: /etc/cloudflared/credentials-file.json
   - vault.yml: keep in your local dev machine or secure storage; do NOT commit to repo. Place at the root of the project directory.
4. Ensure proper permissions: private credentials should be readable only by root or the deploy user: chmod 600 credentials-file.json; chown root:root credentials-file.json
5. After verifying the files are present, remove the tarball from the target machine or move it to encrypted long-term storage.

Security notes:
- Do NOT upload this tarball to cloud storage or include it in git.
- Rotate any keys/secrets if the tarball is lost or the USB is shared.
- The domain smsgraf.vlifecycle.com is private; avoid embedding it in public places.

