from typing import Set, List
from sympy import Expr, Mul, Symbol, Integer, Add, Pow, sympify
from sympy.parsing.sympy_parser import parse_expr
from graph.algorithms.graph import Graph, Branch, Node
from mathematics.signalflow_algorithms.algorithms.johnson import simple_cycles
from graph.algorithms.loop_group import (
    LoopGroup, find_loop_groups)
from graph.algorithms.find_paths import find_paths
from operator import attrgetter
from sympy.abc import _clash


class MasonResult(object):
    def __init__(self):
        self.determinant: List[(Symbol, Expr)] = list()
        self.paths: List[(Symbol, Expr)] = list()
        self.loops: List[(Symbol, Expr)] = list()
        self.numerator: List[(Symbol, Expr)] = list()
        self.denominator: List[(Symbol, Expr)] = list()
        self.transfer_function: List[(Symbol, Expr)] = list()


def mason(graph: Graph, start: Node, end: Node) -> MasonResult:
    # mason = (sum(path[i] * delta[i])) / (delta)
    # delta = 1 - sum of all loops
    #         + sum of products of two loops
    #         - sum of products of three loops
    #         + sum of products of four loops
    #         ....
    # delta: determinante
    # paths[i]: forward path i
    # delta_per_path[i]: delta without loops that touch the forward path i

    result = MasonResult()

    delta = Integer(1)  # Initialize determinante with 1

    # Loops with their corresponding symbol
    loops: List[List[Branch]] = list()
    loop_symbols: List[Symbol] = list()

    # Create a sorted list of simple cycles
    simple_cycle_list = sorted(simple_cycles(graph),
                               key=lambda L: '%s' % (loop_to_expression(L),))
    # Find loops and replace the branch copies with the original branch
    for loop_index, loop in enumerate(simple_cycle_list, start=0):
        new_loop = list()
        for loop_branch in loop:
            branch_iter = iter(graph.branches)
            existing_branch = next(branch_iter)
            while not existing_branch.id == loop_branch.id:
                existing_branch = next(branch_iter)

            new_loop.append(existing_branch)

        loops.append(new_loop)
        loop_symbols.append(Symbol("L" + str(loop_index + 1)))

    for i, loop in enumerate(loops):
        # Add to delta
        delta = Add(delta, Mul(Integer(-1), loop_symbols[i]))
        # Append to loops in result
        result.loops.append((loop_symbols[i], loop_to_expression(loops[i])))

    # Add or substract sum of product of two, three, ... loops
    loop_groups = sorted(find_loop_groups(loops), key=attrgetter('loop_count'))

    for loop_group in loop_groups:
        if loop_group.loop_count > 1:  # Skip loop groups with one member
            expr = Integer(1)

            i = 0
            while i < len(loop_group.loops):
                loop_index = loops.index(loop_group.loops[i])
                expr = Mul(expr, loop_symbols[loop_index])
                i += 1

            # Insert negative sign if necessary
            if loop_group.loop_count % 2 == 1:
                expr = Mul(Integer(-1), expr)

            delta = Add(delta, expr)

    # Summation of products of paths and its determinantes
    paths = find_paths(start, end)

    numerator: Expr = Integer(0)

    # Create a sorted list of paths
    path_list = sorted(paths,
                       key=lambda L: '%s' % (loop_to_expression(L),))
    for i, path in enumerate(path_list, start=1):
        # Create symbol and append to paths in result
        path_symbol = Symbol("P" + str(i))
        result.paths.append((path_symbol, loop_to_expression(path)))

        dpp_symbol = Symbol("D" + str(i))
        dpp = __get_delta_per_path(loops,
                                   loop_symbols,
                                   loop_groups, path)
        # Append to paths in result
        result.paths.append((dpp_symbol, dpp))
        # Add delta_per_path to sum
        numerator = Add(numerator, Mul(path_symbol, dpp_symbol))

    delta_symbol = Symbol("Delta")
    result.determinant = [(delta_symbol, delta)]

    numerator_symbol = Symbol("T_num")
    result.numerator = [(numerator_symbol, numerator)]

    denominator_symbol = Symbol("T_den")
    result.denominator = [(denominator_symbol, delta_symbol)]

    transfer_function_symbol = Symbol("T_io")
    transfer_function = Mul(numerator_symbol, Pow(
        denominator_symbol, Integer(-1)))  # Division
    result.transfer_function = [(transfer_function_symbol, transfer_function)]

    return result


def loop_to_expression(loop: List[Branch]) -> Expr:
    """Create an expression from a loop."""
    if not loop:
        raise ValueError('A loop must contain at least one branch.')

    # Création de l'expression à partir du poids de la première branche de la boucle
    first_weight = loop[0].weight
    # Vérification si le poids est déjà un objet sympy.Expr, ou s'il peut être directement converti en une telle expression
    if isinstance(first_weight, Expr):
        expression = first_weight
    elif isinstance(first_weight, str):
        expression = parse_expr(first_weight, local_dict=_clash)
    else:
        # Pour les nombres ou d'autres types, les convertir en une expression sympy
        expression = sympify(first_weight)

    # Si la boucle contient plus d'une branche, multiplier l'expression par le poids de chaque branche supplémentaire
    for branch in loop[1:]:
        next_weight = branch.weight
        # Application de la même logique de conversion pour le poids de chaque branche suivante
        if isinstance(next_weight, Expr):
            next_expr = next_weight
        elif isinstance(next_weight, str):
            next_expr = parse_expr(next_weight, local_dict=_clash)
        else:
            next_expr = sympify(next_weight)
        expression *= next_expr

    return expression


def __get_delta_per_path(
        loops: List[List[Branch]],
        loop_symbols: List[Symbol],
        loop_groups: List[LoopGroup],
        path: List[Branch]):

    delta = Integer(1)  # Initialize subdeterminante with 1

    for index, loop in enumerate(loops):
        if not __loop_touches_path(loop, path):
            delta = Add(delta, Mul(Integer(-1), loop_symbols[index]))

    for loop_group in loop_groups:
        if loop_group.loop_count > 1:  # Skip loop groups with one member
            expr = Integer(1)

            i = 0
            not_touches = True
            while i < len(loop_group.loops):
                loop = loop_group.loops[i]
                if not __loop_touches_path(loop, path):
                    loop_index = loops.index(loop)
                    expr = Mul(expr, loop_symbols[loop_index])
                else:
                    not_touches = False

                i += 1

            # Insert negative sign if necessary
            if loop_group.loop_count % 2 == 1:
                expr = Mul(Integer(-1), expr)

            if not_touches:
                delta = Add(delta, expr)

    return delta


def __loop_touches_path(loop: List[Branch], path: List[Branch]) -> bool:
    loop_nodes: Set[Node] = set()

    for cbranch in loop:
        loop_nodes.add(cbranch.start)
        loop_nodes.add(cbranch.end)

    path_nodes: Set[Node] = set()

    for pbranch in path:
        path_nodes.add(pbranch.start)
        path_nodes.add(pbranch.end)

    return len(path_nodes.intersection(loop_nodes)) > 0
