"""MCDR 2.16 command graph adapter. Execution/completion always use MCDR itself."""
import json
from mcdreforged.command.builder.nodes.basic import Literal, ArgumentNode


def command_tree(server):
    nodes = []
    visited = {}
    def export(node):
        if id(node) in visited:
            return visited[id(node)]
        if isinstance(node, Literal):
            records = [dict(kind='literal', name=name) for name in sorted(node.literals)]
        elif isinstance(node, ArgumentNode):
            records = [dict(kind='argument', name=node.get_name(), greedy=type(node).__name__ == 'GreedyText')]
        else:
            return []
        ids = list(range(len(nodes), len(nodes) + len(records)))
        visited[id(node)] = ids
        nodes.extend(records)
        children = [value for child in node.get_children() for value in export(child)]
        redirects = export(node._redirect_node) if node._redirect_node is not None else []
        for record in records:
            record.update(children=children, redirect=redirects[0] if redirects else None)
        return ids
    roots = []
    for name, holders in sorted(server._mcdr_server.command_manager.root_nodes.items()):
        for holder in holders:
            roots.extend(index for index in export(holder.node) if nodes[index]['name'] == name)
    return json.dumps(dict(roots=roots, nodes=nodes), ensure_ascii=False, separators=(',', ':'))
