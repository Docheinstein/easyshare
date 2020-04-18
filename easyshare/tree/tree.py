from typing import List, Any, Union, Dict, Tuple

from easyshare.utils.env import is_unicode_supported

try:
    # From python 3.8
    from typing import TypedDict

    class TreeNodeDict(TypedDict, total=False):
        children: List['TreeNodeDict']

except:
    TreeNodeDict = Dict[str, Union[Any, List['TreeNodeDict']]]


class TreeRenderStyle:
    def __init__(self,
                 vertical: str, horizontal: str,
                 branch: str, last_branch: str,
                 stretching: int, spacing: int):
        self.vertical = vertical
        self.horizontal = horizontal
        self.branch = branch
        self.last_branch = last_branch
        self.stretching = stretching
        self.spacing = spacing


class TreeRenderStyleUnicode(TreeRenderStyle):
    def __init__(self, stretching: int = 2, spacing: int = 1):
        super().__init__(vertical="\u2502",
                         horizontal="\u2500",
                         branch="\u251c",
                         last_branch="\u2514",
                         stretching=stretching,
                         spacing=spacing)


class TreeRenderStyleAscii(TreeRenderStyle):
    def __init__(self, stretching: int = 2, spacing: int = 1):
        super().__init__(vertical="|",
                         horizontal="-",
                         branch="|",
                         last_branch="+",
                         stretching=stretching,
                         spacing=spacing)


class TreeRenderStyleFactory:
    @staticmethod
    def ascii(stretching: int = 2, spacing: int = 1) -> TreeRenderStyle:
        return TreeRenderStyleAscii(stretching=stretching, spacing=spacing)

    @staticmethod
    def unicode(stretching: int = 2, spacing: int = 1) -> TreeRenderStyle:
        return TreeRenderStyleUnicode(stretching=stretching, spacing=spacing)

    @staticmethod
    def auto(stretching: int = 2, spacing: int = 1) -> TreeRenderStyle:
        if is_unicode_supported():
            return TreeRenderStyleFactory.unicode(stretching, spacing)
        return TreeRenderStyleFactory.ascii(stretching, spacing)


class TreeRenderPostOrder:
    def __init__(self,
                 root: TreeNodeDict,
                 depth: int = None,
                 style: TreeRenderStyle = TreeRenderStyleFactory.auto()):
        self.root = root
        self.depth = depth
        self.style = style
        self.depth = 0

    def __iter__(self):

        self.traverse_stack = [(self.root, self.depth)]
        self.last_of_depth = [0]

        return self

    def __next__(self) -> Tuple[str, TreeNodeDict, int]:  # prefix, node, depth
        if not self.traverse_stack:
            raise StopIteration()

        node, depth = None, None

        while self.traverse_stack:
            node, depth = self.traverse_stack.pop()
            if not self.depth or depth <= self.depth:
                break

        if not node or (self.depth and depth > self.depth):
            raise StopIteration()

        # Adjust last_of_depth size
        # 1. Append zeros if is shorted than 'depth'
        # 2. Remove trailing if is longer than 'depth'
        self.last_of_depth += max(0, (depth - len(self.last_of_depth))) * [0]
        self.last_of_depth = self.last_of_depth[:depth]

        # noinspection PyChainedComparisons
        last_branch_of_depth = True if (
                depth > 0 and
                (not self.traverse_stack or
                 (self.traverse_stack[len(self.traverse_stack) - 1][1] != depth))
        ) else False

        # See ahead for decide whether the node is the last of the depth layer
        if depth > 0:
            # Is last of the depth if
            # 1. There is nothing left to see (only the really last node)
            # 2. The next node (visit_stack[len(visit_stack) - 1])
            #    has a different depth (...[1])
            self.last_of_depth[depth - 1] = int(last_branch_of_depth)

        prefix = ""
        d = 0
        while d < len(self.last_of_depth):
            if d == len(self.last_of_depth) - 1:
                vmark = self.style.last_branch if last_branch_of_depth else self.style.branch
                hmark = self.style.horizontal
            else:
                vmark = self.style.vertical if self.last_of_depth[d] == 0 else " "
                hmark = " "
            prefix += "{}{}{}".format(vmark,
                                      hmark * self.style.stretching,
                                      " " * self.style.spacing)
            d += 1

        # Push the children to the stack, in reversed order
        if node.get("children"):
            for child in reversed(node.get("children")):
                self.traverse_stack.append((child, depth + 1))

        return prefix, node, depth
