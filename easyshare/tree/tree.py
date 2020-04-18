from typing import List, Any, Union, Dict, Callable

try:
    # From python 3.8
    from typing import TypedDict

    class TreeNodeDict(TypedDict, total=False):
        children: List['TreeNodeDict']

except:
    TreeNodeDict = Dict[str, Union[Any, List['TreeNodeDict']]]


def preorder_traversal(root: TreeNodeDict,
                       on_visit: Callable[[str, TreeNodeDict, List[str]], None],
                       vertical: str = "\u2502",
                       horizontal: str = "\u2500",
                       cross: str = "\u251c",
                       end: str = "\u2514",
                       stretching: int = 2,
                       spacing: int = 1):
    depth = 0
    node = root

    visit_stack = [(node, depth)]
    last_of_depth = [0]

    while visit_stack:
        node, depth = visit_stack.pop()

        # Adjust last_of_depth size
        # 1. Append zeros if is shorted than 'depth'
        # 2. Remove trailing if is longer than 'depth'
        last_of_depth += max(0, (depth - len(last_of_depth))) * [0]
        last_of_depth = last_of_depth[:depth]

        # noinspection PyChainedComparisons
        last_branch_of_depth = True if (
                depth > 0 and (not visit_stack or (visit_stack[len(visit_stack) - 1][1] != depth))
        ) else False

        # See ahead for decide whether the node is the last of the depth layer
        if depth > 0:
            # Is last of the depth if
            # 1. There is nothing left to see (only the really last node)
            # 2. The next node (visit_stack[len(visit_stack) - 1])
            #    has a different depth (...[1])
            last_of_depth[depth - 1] = int(last_branch_of_depth)

        prefix = ""
        d = 0
        while d < len(last_of_depth):
            if d == len(last_of_depth) - 1:
                vmark = end if last_branch_of_depth else cross
                hmark = horizontal
            else:
                vmark = vertical if last_of_depth[d] == 0 else " "
                hmark = " "
            prefix += "{}{}{}".format(vmark, hmark * stretching, " " * spacing)
            d += 1

        on_visit(prefix, node, last_of_depth)

        if node.get("children"):
            for child in reversed(node.get("children")):
                visit_stack.append((child, depth + 1))
