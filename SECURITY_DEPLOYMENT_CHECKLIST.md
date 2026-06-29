# Phase 8 Security Deployment Checklist

1. Set a strong SECRET_KEY in Render.
2. Change all default/admin passwords.
3. Keep DATABASE_URL only in Render environment variables.
4. Move FICA/signature uploads to permanent cloud storage before heavy production use.
5. Configure daily PostgreSQL backups.
6. Disable AUTO_CREATE_TABLES after proper migrations are fully tested.
7. Do not upload ZIPs containing a .git folder.
8. Review inactive users weekly.
