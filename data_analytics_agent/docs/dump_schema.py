"""
Script to introspect demo_data/demo.db and generate docs/schema_snapshot.md.
"""
import sqlite3

def generate_snapshot():
    conn = sqlite3.connect("demo_data/demo.db")
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    tables = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='view' ORDER BY name;")
    views = cur.fetchall()

    lines = [
        "# Database Schema Snapshot: demo_data/demo.db",
        "",
        "This document records the exact introspected schema (`PRAGMA table_info`, `PRAGMA foreign_key_list`) from `demo_data/demo.db` as required by the Business Intel Agent specification.",
        "",
        f"**Total Tables:** {len(tables)}  ",
        f"**Total Views:** {len(views)}  ",
        "",
        "---",
        "",
        "## Tables",
        ""
    ]

    for tbl in tables:
        cur.execute(f"SELECT COUNT(*) FROM {tbl};")
        count = cur.fetchone()[0]
        lines.append(f"### `{tbl}` ({count} rows)")
        lines.append("")
        lines.append("| # | Column | Type | NotNull | Default | PK |")
        lines.append("|---|---|---|---|---|---|")
        cur.execute(f"PRAGMA table_info({tbl});")
        cols = cur.fetchall()
        for c in cols:
            default_val = c[4] if c[4] is not None else "NULL"
            lines.append(f"| {c[0]} | `{c[1]}` | {c[2]} | {bool(c[3])} | {default_val} | {bool(c[5])} |")
        
        # foreign keys
        cur.execute(f"PRAGMA foreign_key_list({tbl});")
        fks = cur.fetchall()
        if fks:
            lines.append("")
            lines.append("**Foreign Keys:**")
            for fk in fks:
                lines.append(f"- `{fk[3]}` -> `{fk[2]}({fk[4]})`")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Views")
    lines.append("")
    for vname, vsql in views:
        lines.append(f"### `{vname}`")
        lines.append("```sql")
        lines.append(vsql.strip())
        lines.append("```")
        lines.append("")

    with open("docs/schema_snapshot.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated docs/schema_snapshot.md with {len(tables)} tables and {len(views)} views.")

if __name__ == "__main__":
    generate_snapshot()

