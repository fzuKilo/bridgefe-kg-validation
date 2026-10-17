"""可执行公式的安全求值器。

规范条文与建模规则中的公式以表达式字符串存放在知识图谱节点上，由本模块求值。
只允许算术、比较、布尔、条件表达式、下标（查表）与白名单函数，不执行任意代码。
"""
import ast
import math

FUNCS = {
    'min': min, 'max': max, 'abs': abs, 'round': round,
    'sqrt': math.sqrt, 'log': math.log, 'exp': math.exp, 'pi': math.pi,
}

_BIN = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b,
}
_CMP = {
    ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}


class ExprError(ValueError):
    pass


def evaluate(expr, env):
    """在变量环境 env 中对表达式求值。缺失变量抛出 ExprError 并给出变量名。"""
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise ExprError(f'公式语法错误: {expr}') from e
    return _eval(tree.body, env)


def _eval(node, env):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in FUNCS:
            return FUNCS[node.id]
        if node.id in ('True', 'False', 'None'):
            return {'True': True, 'False': False, 'None': None}[node.id]
        raise ExprError(f'缺少输入参数: {node.id}')
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.UAdd):
            return v
    if isinstance(node, ast.BoolOp):
        vals = (_eval(v, env) for v in node.values)
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, env)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval(node.test, env) else _eval(node.orelse, env)
    if isinstance(node, ast.Subscript):
        return _eval(node.value, env)[_eval(node.slice, env)]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS:
        return FUNCS[node.func.id](*[_eval(a, env) for a in node.args])
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval(e, env) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {_eval(k, env): _eval(v, env) for k, v in zip(node.keys, node.values)}
    raise ExprError(f'不支持的表达式成分: {ast.dump(node)[:60]}')


def names(expr):
    """表达式引用的变量名（用于列出条文输入参数）。"""
    return sorted({n.id for n in ast.walk(ast.parse(expr, mode='eval'))
                   if isinstance(n, ast.Name) and n.id not in FUNCS})
