# SmartTutor Backend — Setup Guide

This guide walks you through setting up the SmartTutor FastAPI + PostgreSQL backend on your machine after cloning the repo. Follow the steps in order — don't skip ahead, later steps depend on earlier ones.

---

## Prerequisites

Before starting, make sure you have installed:

- **Python 3.12+** — check with `python --version`
- **Git** — check with `git --version`
- **PostgreSQL** (server + pgAdmin, or Docker if the team uses that instead) — check with `psql --version` if installed locally
- A code editor (VS Code recommended)

If any of these are missing, install them first and confirm the version commands work before continuing.

---

## 1. Clone the repository

```bash
git clone <REPO_URL>
cd smarttutor-backend
```

Replace `<REPO_URL>` with the actual GitHub URL for this project.

---

## 2. Confirm the project structure

Run:

```bash
ls -a
```

You should see something like:

```
app/
alembic/
alembic.ini
requirements.txt
.env.example
.gitignore
README.md
```

You will **not** see `.env` or `venv/` — these are intentionally excluded from the repo (see Step 5 and Step 3 below for why).

---

## 3. Create and activate a virtual environment

A venv keeps this project's Python packages isolated from everything else on your machine.

```bash
python -m venv venv
```

Activate it:

```bash
# Git Bash (Windows)
source venv/Scripts/activate

# PowerShell / cmd (Windows)
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

Your terminal prompt should now show `(venv)` at the start of the line. **You need to activate this every time you open a new terminal to work on this project** — if a command later says "not found," this is the first thing to check.

---

## 4. Install dependencies

With the venv active:

```bash
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, Alembic, psycopg2, and everything else the project needs, at the exact versions everyone on the team is using.

---

## 5. Set up your environment variables

Copy the example file:

```bash
cp .env.example .env
```

Open `.env` in your editor. It will look like this:

```
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=smarttutor
POSTGRES_SCHEMA=smarttutor
```

Fill in **your own** values (you'll create the matching Postgres user in Step 6). Do not use anyone else's password. This file is gitignored — it stays local to your machine and is never pushed.

---

## 6. Set up PostgreSQL

You need your own local Postgres user and database, matching whatever you put in `.env`.

### Using pgAdmin

1. Open pgAdmin and connect to your local Postgres server (it will ask for your Postgres **superuser** password — the one set when Postgres was installed).
2. **Create the login role:**
   - Right-click **Login/Group Roles** → **Create** → **Login/Group Role**
   - **General tab** → Name: matches `POSTGRES_USER` in your `.env` (e.g. `smarttutor_user`)
   - **Definition tab** → Password: matches `POSTGRES_PASSWORD` in your `.env`
   - **Privileges tab** → toggle **Can login?** to **Yes**
   - **Save**
3. **Create the database:**
   - Right-click **Databases** → **Create** → **Database**
   - Database name: matches `POSTGRES_DB` (e.g. `smarttutor`)
   - Owner: select the role you just created
   - **Save**

> Do **not** manually create the `smarttutor` schema inside the database — Alembic creates it automatically in the next step.

---

## 7. Apply the database migrations

The table structure (schema) for this project is already defined and committed in `alembic/versions/`. You do **not** need to write new migrations — you just need to apply the existing ones to your fresh, empty database.

```bash
alembic upgrade head
```

This will:
- Connect to your database using the credentials in `.env`
- Automatically create the `smarttutor` schema
- Create all tables (`user_roles`, `users`, `questions`, `lov`, `answers`, and any others added since)
- Record which migrations have been applied, in an `alembic_version` table

You should see output like:

```
INFO  [alembic.runtime.migration] Running upgrade  -> ab5e080a4a10, init schema
```

**Verify in pgAdmin:** refresh your database → expand **Schemas** → `smarttutor` → **Tables**. You should see all the project's tables listed, empty (no rows) but structurally complete.

> ⚠️ **Important distinction:** this step recreates the *table structure* only — column names, types, foreign keys, constraints. It does **not** copy anyone else's actual data (users, questions, etc.). Everyone's local database starts empty. If you need sample data to test with, ask the team whether a seed script exists, or create your own test records through the API.

---

## 8. Run the application

```bash
uvicorn app.main:app --reload
```

Open your browser to:

```
http://localhost:8000/docs
```

You should see the full Swagger UI with all endpoints listed (User Roles, Users, LOV, Questions, Answers, and any others). Try a `POST /admin/user-roles/` request to confirm everything is wired up end to end.

---

## Everyday workflow after initial setup

Once set up, your regular routine when returning to the project is:

```bash
cd smarttutor-backend
source venv/Scripts/activate      # or your platform's equivalent
git pull                          # get the latest code
alembic upgrade head              # apply any new migrations that came in
uvicorn app.main:app --reload     # run the server
```

---

## If the database schema changes (model files are updated)

Whenever `app/models.py` changes on the team (e.g. someone adds a new column or table) and you `git pull` that change:

```bash
alembic upgrade head
```

is all you need to run — this applies whatever new migration file(s) came in with the pull. **Do not** run `alembic revision --autogenerate` yourself unless *you* are the one who changed `models.py` and need to generate a *new* migration to commit for others.

---

## Troubleshooting

| Error | Likely cause |
|---|---|
| `ModuleNotFoundError: No module named 'app...'` | Your venv isn't activated, or you're running the command from the wrong folder. Confirm `(venv)` shows in your prompt and `pwd`/`cd` shows you're in the project root. |
| `psycopg2.OperationalError: role "..." does not exist` | The Postgres login role from Step 6 wasn't created, or doesn't match `.env`. |
| `password authentication failed` | The password in `.env` doesn't match what you set in pgAdmin for that role. |
| Swagger shows some endpoints missing | A router file may be incomplete — check the relevant file in `app/routers/`. |
| `alembic.util.exc.CommandError: Can't locate revision...` | Your local `alembic_version` table is out of sync — ask a teammate or check the `alembic/versions/` history before resolving, don't guess. |

---

## Questions?

If you hit an error not covered here, check the full traceback carefully — the last few lines usually point to the exact file and line causing the problem. Ask the team with the full error pasted in, not just a description of it.
