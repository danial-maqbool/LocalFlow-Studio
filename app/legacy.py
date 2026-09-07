"""Convert the first public step-list format without executing it."""

import json
from localdesk.safety import InputError


def convert(workflow):
    if not isinstance(workflow, dict) or "steps" not in workflow or "nodes" in workflow:
        return workflow
    steps = workflow["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 40:
        raise InputError("A legacy workflow needs 1 to 40 steps.")
    nodes = []
    for index, value in enumerate(steps):
        if not isinstance(value, dict):
            raise InputError("A legacy step must be an object.")
        node = json.loads(json.dumps(value))
        node.setdefault("id", str(index))
        node.setdefault("config", {})
        if node.get("type") == "rename":
            node["type"] = "name"
        if node.get("type") in {"csv", "archive"} and "name" in node["config"]:
            node["config"]["filename"] = node["config"].pop("name")
        node.setdefault("position", {"x": 80 + index * 210, "y": 100})
        nodes.append(node)
    return {
        **{k: v for k, v in workflow.items() if k != "steps"},
        "nodes": nodes,
        "edges": [
            {"from": nodes[i]["id"], "to": nodes[i + 1]["id"]} for i in range(len(nodes) - 1)
        ],
    }


def upgrade_schema(store):
    columns = {r["name"] for r in store.rows("PRAGMA table_info(workflows)")}
    if not columns or "revision" in columns:
        return
    if not {"id", "name", "body", "updated"} <= columns:
        raise InputError("This legacy workflow database schema is not recognized.")
    from .engine import validate
    from localdesk.jobs import utcnow

    with store.connection() as db:
        db.execute("ALTER TABLE workflows ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
        for row in list(db.execute("SELECT id,name,body FROM workflows")):
            workflow = convert(json.loads(row["body"]))
            workflow.update({"id": row["id"], "name": row["name"], "version": 1})
            validate(workflow)
            db.execute(
                "UPDATE workflows SET body=?,updated=? WHERE id=?",
                (json.dumps(workflow), utcnow(), row["id"]),
            )
