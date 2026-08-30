# Canvas Quizbot
Discord bot that automatically rotates access codes on Canvas quizzes on a schedule. Supports both Classic Quizzes and New Quizzes engines, one-shot and recurring (cron) schedules, and multiple schedules per quiz.

## Features
- Scheduled access code rotation
- Supports both quiz engines
- Startup reconciliation

## Requirements
- Python 3.12+
- A Discord bot token with the `applications.commands` scope and `bot` scope
- A Canvas API token with permission to edit quiz settings
- (Optional) Docker and Docker Compose (recommended for deployment)

## Quick Start (Docker Compose)

1. **Clone the repository**

   ```sh
   git clone https://github.com/your-org/canvas-quizbot.git
   cd canvas-quizbot
   ```

2. **Create your `.env` file** from the provided example:

   ```sh
   cp .env.example .env
   ```

   Then fill in all required values (see [Environment Variables](#environment-variables) below).

3. **Start the bot**

   ```sh
   docker compose up -d
   ```

   The SQLite database is stored in a named Docker volume (`quizbot-data`) and persists across container restarts.

## Environment Variables

Copy `.env.example` to `.env` and set the following:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Discord bot token |
| `CANVAS_TOKEN` | Yes | — | Canvas API token (never logged or stored) |
| `ADMIN_DISCORD_ID` | Yes | — | Discord user ID to DM on rotation failures |
| `CANVAS_BASE_URL_DEV` | Yes | — | Canvas beta instance URL (no trailing slash) |
| `CANVAS_BASE_URL_PROD` | Yes | — | Canvas production instance URL (no trailing slash) |
| `APP_MODE` | No | `development` | Set to `production` to use the production Canvas URL |
| `DB_URL` | No | `sqlite:////data/quizbot.db` | SQLAlchemy database URL |
| `CODE_LENGTH` | No | `6` | Length of randomly generated access codes |
| `ONESHOT_LATE_GUARD_HOURS` | No | `24` | Hours before a one-shot schedule's run time at which late scheduling is rejected |

> **Security note:** `CANVAS_TOKEN` is loaded from the environment only. It is never written to the database, logged, or sent to Discord.

## Discord Commands

All commands are under the `/qb` group. Access requires a configured allowed role (or the admin user).

### Quizzes

| Command | Description |
|---|---|
| `/qb quizzes list` | List registered quizzes (use `show_all:True` to include quizzes with no active schedule) |
| `/qb quizzes add <url>` | Register a Canvas quiz by URL (auto-detects Classic vs New Quizzes engine) |
| `/qb quizzes delete <quiz>` | Remove a quiz (and all its schedules) by URL or numeric ID |

### Schedules

| Command | Description |
|---|---|
| `/qb schedules list` | List active schedules (use `show_all:True` to include expired ones) |
| `/qb schedules add <quizids> [options]` | Add a schedule to one or more quizzes |
| `/qb schedules update <schedule_id> [options]` | Modify an existing schedule |
| `/qb schedules delete <schedule_id>` | Delete a schedule |

**Schedule options:**

- `cron` — 5-field cron expression (e.g. `0 8 * * 1` for every Monday at 08:00)
- `at` — one-shot datetime (e.g. `2026-09-01 08:00`)
- `start` / `end` — optional window for recurring schedules (ISO 8601 datetime)
- `random` — `True` to generate a random code each rotation (default)
- `code` — fixed code to use instead of a random one

All times are interpreted as **America/New_York**.

### Codes

| Command | Description |
|---|---|
| `/qb codes list` | List quizzes that currently have an access code set |
| `/qb codes update <quizids> [random] [code]` | Immediately rotate the code on one or more quizzes |

### Configuration

| Command | Description |
|---|---|
| `/qb config show` | Show current configuration |
| `/qb config set-channel <channel>` | Set the channel for rotation notifications |
| `/qb config add-role <role>` | (Admin only) Allow a role to use bot commands |
| `/qb config remove-role <role>` | (Admin only) Remove a role from the allowed list |

## Development Setup

```sh
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest
```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2. Under **Bot**, create a bot and copy the token into `DISCORD_TOKEN`.
3. Under **OAuth2 → URL Generator**, select scopes `bot` and `applications.commands`. Grant the bot **Send Messages**, **Embed Links**, and **Use Application Commands** permissions.
4. Invite the bot to your server using the generated URL.
5. After the bot starts, use `/qb config add-role` to grant a role access to commands.

## License

MIT — see [LICENSE](LICENSE).