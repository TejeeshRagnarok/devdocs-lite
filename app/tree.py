def build_tree(entries: list[dict]) -> list[dict]:
    root: dict[str, dict] = {}

    for entry in entries:
        current = root
        parts = entry["path"].split("/")
        for part in parts[:-1]:
            current = current.setdefault(
                part,
                {"name": part, "type": "directory", "children": {}},
            )["children"]
        current[parts[-1]] = {
            "name": parts[-1],
            "path": entry["path"],
            "type": "file",
            "language": entry["language"],
            "lines": entry["lines"],
        }

    def sort_node(node: dict) -> list[dict]:
        children = []
        for item in node.values():
            if item["type"] == "directory":
                item = {**item, "children": sort_node(item["children"])}
            children.append(item)
        return sorted(children, key=lambda item: (item["type"] == "file", item["name"].lower()))

    return sort_node(root)
