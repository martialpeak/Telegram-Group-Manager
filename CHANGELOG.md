# Changelog

All notable changes to this project will be documented here.

---

## [2.0.0] — 2025

### Added
- **Bilingual installer** (`install.sh`) — choose English or Finglish during setup
- **Bot language selection** — Persian (fa) or English (en) via `/settings` or installer
- **i18n system** (`i18n.py`) — centralized translation for all bot messages
- **User level system** — 5 tiers: simple / bronze / silver / gold / diamond
- **Auto-upgrade** — simple → bronze after 50 messages (automatic)
- **Member tags** — `setChatMemberTag` API sets visible tags per level
- **Status tags** — ⚠️ warning tags, 🔇 mute tags via `setChatMemberTag`
- **Escalating mute** — 10m → 30m → 3h → 24h → 48h per repeat offense
- **Escalating ban** — 1d → 3d → 7d → 30d → permanent per repeat offense
- **Temporary ban** — `/ban 30m`, `/ban 2h`, `/ban 7d` syntax
- **Report system** — `/report` with admin PM notification + action buttons
- **Settings panel** — `/settings` inline keyboard for admins (Telegram-based config)
- **Daily stats** — `/mystats` with progress bars for users
- **Admin stats** — `/stats` (daily + total) and `/violations` with top offenders
- **Welcome/leave messages** — auto-delete after configurable delay
- **Message auto-delete** — warnings, limit notices auto-deleted after seconds
- **Daily limits** — link/forward/query quotas per level (enforced, not punished)
- **Community corrections** — vote-based learning from user feedback

### Changed
- `/stats` now shows today vs. all-time breakdown
- Spam handling now uses escalating mute instead of fixed 10 min
- Level configs updated: silver/gold/diamond now have tiered daily forwards/links
- All bot messages now go through `i18n.t()` for language switching

### Fixed
- Duplicate `welcome` key in `config.py` MESSAGES dict
- `_send_and_delete` now properly schedules async deletion

---

## [1.0.0] — Initial Release

### Added
- AI-powered message analysis (Ollama — local, no API key)
- Insult and spam detection with fallback rule engine
- Warning system with auto-ban
- Knowledge base with semantic search
- User feedback and community correction system
- SQLite database for all data
- Admin commands: warn, ban, unwarn, stats, search
