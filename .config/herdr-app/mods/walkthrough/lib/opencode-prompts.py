import json, os, sqlite3, sys

# The prompts typed into opencode sessions working in a repository since a moment,
# and when any of those sessions last wrote.
# Use: python3 opencode-prompts.py <repo-top> <since-ms> [<database>]
#
# Prints {"prompts": [{"at", "text", "session"}], "active": <ms>}, or, when the
# database is there but isn't laid out as expected (opencode's tables are
# undocumented and may change), {"error": "..."} and exits with 2.

top, since = sys.argv[1], int(sys.argv[2])
db = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/.local/share/opencode/opencode.db")
if not os.path.exists(db):
    print(json.dumps({"prompts": [], "active": 0}))
    sys.exit(0)

# A prefix compared as text: in LIKE, "_" and "%" in the path would be wildcards.
inside = "(s.directory = ? or substr(s.directory, 1, ?) = ?)"
where = (top, len(top) + 1, top + "/")
try:
    con = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
    rows = con.execute(
        "select m.session_id, m.time_created, m.data from session_message m "
        "join session_v2 s on s.id = m.session_id "
        "where m.type = 'user' and " + inside + " and m.time_created >= ? "
        "order by m.time_created",
        (*where, since),
    ).fetchall()
    active = con.execute(
        "select max(m.time_created) from session_message m "
        "join session_v2 s on s.id = m.session_id where " + inside,
        where,
    ).fetchone()[0]
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(2)

prompts = []
for sid, at, data in rows:
    try:
        text = (json.loads(data or "{}").get("text") or "").strip()
    except Exception:
        continue
    if text:
        prompts.append({"at": int(at or 0), "text": text, "session": sid})
print(json.dumps({"prompts": prompts, "active": int(active or 0)}))
