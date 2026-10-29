# Security and privacy

## Implemented
- **Secrets:** API keys are read only from `.env` or environment variables. `.env` is git-ignored, and `.env.example` contains no real values. Keys are never shown in the UI, stored in SQLite or written to the usage log (tested: a failing request's log row does not contain the key).
- **Local data:** `data/ecalc.db` (projects, calculations, documents, usage) is git-ignored. Business trackers containing prospect contacts go in `business/private/` (git-ignored).
- **Uploads:** only `.pdf`, `.txt` and `.md`; size limit (default 20 MB); a PDF signature check; encrypted PDFs are rejected; empty or scanned files are rejected with a clear message.
- **Prompt injection:** document passages are wrapped in `<document>` tags, and a user cannot close the tag early (escaped). The system prompt tells the model to treat them as untrusted data. Instruction-like text in an upload triggers a visible warning.
- **External disclosure:** document excerpts go to a cloud AI only after the user ticks an explicit authorisation box naming the provider. Offline and Ollama modes keep everything on the computer. The Gemini free-tier data-use warning is displayed.
- **Cost safety:** paid providers are blocked unless a monthly budget is set; there is a per-request worst-case cost cap; there is no silent fallback to another provider; OpenRouter is limited to `:free` models.
- **Network:** the app binds to localhost by default. Timeouts apply to all external calls (PVGIS 30 s, AI 60 s default).

## Not yet implemented (needed before public hosting)
- User authentication and per-customer data separation (Streamlit has no built-in auth; use a proxy or Streamlit's OIDC login when deploying).
- Encryption at rest for the SQLite file.
- Rate limiting per user.
- Automated backups (manual for now: copy `data/ecalc.db` while the app is stopped).
- OCR and malware scanning of uploads.

## Backup and recovery
1. Stop the app.
2. Copy `data/ecalc.db` to a backup folder or USB drive, named with the date.
3. To restore, stop the app and copy the backup back to `data/ecalc.db`.
