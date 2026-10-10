# Alexa Business Autopilot — Agent & Development Guidelines

This document defines the permanent development principles, architectural boundaries, and workflow procedures for the **Alexa Business Autopilot** project. All AI assistants, pair programmers, and contributors must adhere to these rules.

---

## 1. Project Mission & Identity

- **General-Purpose AI Business Autopilot**: This project is an autonomous operating and decision layer for Indian micro and small businesses across diverse verticals (retail, kirana, services, food/catering, light manufacturing, and distribution).
- **Domain Scope**: Food delivery / tiffin service (`home_tiffin`) is strictly **one illustrative example** used for initial testing and demonstration. It is **not** the project's definition or limit. Business logic, data models, and agent capabilities must remain domain-agnostic or extensible across business profiles.
- **Backend-Only Architecture**: The project is strictly **frontend-free**. Do not build, restore, redesign, or maintain any HTML/CSS/JS frontend. The application interface consists solely of FastAPI HTTP endpoints and Model Context Protocol (MCP) server endpoints for voice/chat integration.

---

## 2. Agent & Architecture Guarantees

- **Genuine LLM Autonomy**: The system must genuinely invoke an LLM (e.g., Google Gemini via official SDKs) with dynamic function calling and tool execution. Deterministic calculators, simulators, and heuristics are tools for the model to use—they must **never** be misrepresented as an autonomous AI agent.
- **Teammate Ownership of Database**: Database development, schema definitions, bulk seeding, and reference queries in `data/` (such as `data/schema.sql`, `data/build_db.py`, `data/business.db`, `data/demo.db`) are **owned by teammates**.
  - Do **not** redesign, replace, or duplicate teammates' database work.
  - Work collaboratively with existing schemas and tools rather than inventing parallel storage systems.
- **Clean Separation of Concerns**:
  - `src/decision/`: Business decision logic, cash/liquidity safety validation, approval state machine.
  - `src/db/`: Persistence repositories, database connections, and migrations.
  - `src/models/`: Domain dataclasses and business profile models.
  - `src/server/`: FastAPI web application and MCP server protocol endpoints.
  - `src/services/` & `src/engine/`: Value-chain simulators and supplier simulators.

---

## 3. Safe Pre-Task Repository Review Procedure

Before modifying code or executing tasks, the AI assistant **must** execute the following checklist:

1. **Inspect Working Tree**:
   - Check `git status --short`, active branch (`git branch --show-current`), and tracking branch (`git branch -vv`).
   - Identify any existing staged, unstaged, or untracked changes. Preserve in-progress work; never use destructive commands like `git reset --hard` or `git clean -fd` without explicit instruction.
2. **Check Remote Synchronization**:
   - Run `git fetch origin` when appropriate to inspect remote tracking.
   - Check whether `origin` contains newer commits (`git log HEAD..origin/<branch> --oneline`).
   - If remote changes exist and local work is dirty or divergent, **stop and report** the discrepancy to the user before attempting any merge or rebase. Never silently overwrite local or remote work.
3. **Inspect Real Code First**:
   - Always read the actual target source files, tests, and configuration before editing. Do not rely on memory or assumptions from earlier conversational summaries.
   - Check existing implementations before creating new classes, tools, routes, or helper functions to avoid duplicates.
4. **Test Verification**:
   - Run the relevant pytest suite after code edits.
   - Report pass/fail counts accurately. Never mask or delete tests to fake passing builds.

---

## 4. Git Synchronization & Push Policy

- **No Automatic Pushing**: Commits and pushes must **never** be performed automatically on file save or task completion without explicit user authorization.
- **Checkpoint-Based Workflow**: Work should proceed in reviewable phases. When a phase is complete and verified with passing tests, propose a staged commit with a clear, descriptive message (e.g., Conventional Commits format).
- **Push Safety Rules**:
  - Push target must always be verified: `https://github.com/milindbathla/Amazom_Developer_Hackathon.git`.
  - Never force-push (`--force`) or rewrite published remote history.
  - If a pull is needed, use safe fast-forward mechanisms (`git pull --ff-only`) or explain the merge strategy beforehand.
- **Security & Secret Sanitation**:
  - Never commit `.env`, API keys (`GEMINI_API_KEY`, etc.), bearer tokens, or credentials.
  - Keep local database files (`*.sqlite3*`, `*.db*`), vector stores (`data/chroma/`), build artifacts, and cache directories in `.gitignore`.
  - Always run `git diff --cached --check` and audit staged files before committing.
