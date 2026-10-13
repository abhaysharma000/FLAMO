"""Calculator tool with safe arithmetic and division-by-zero protection."""

import ast
import operator
from typing import Optional, Union
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Supported safe binary operators for expression evaluation
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_expr(node: ast.AST) -> Union[int, float]:
    """Safely evaluate an AST math expression without allowing arbitrary code execution."""
    if isinstance(node, ast.Expression):
        return safe_eval_expr(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = safe_eval_expr(node.left)
        right = safe_eval_expr(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Cannot divide by zero.")
        return SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = safe_eval_expr(node.operand)
        return SAFE_OPERATORS[op_type](operand)
    else:
        raise ValueError(f"Unsupported expression element: {type(node).__name__}")


class CalculatorInput(BaseModel):
    """Input parameters for mathematical calculations."""

    a: Optional[float] = Field(default=None, description="First number for binary operation")
    b: Optional[float] = Field(default=None, description="Second number for binary operation")
    operation: Optional[str] = Field(
        default=None,
        description="Operation name: 'add', 'subtract', 'multiply', 'divide', 'power', or 'modulo'"
    )
    expression: Optional[str] = Field(
        default=None,
        description="Optional full math expression string, e.g. '125 * 48' or '(125 * 48) / 5'"
    )


@tool(args_schema=CalculatorInput)
def calculator(
    a: Optional[float] = None,
    b: Optional[float] = None,
    operation: Optional[str] = None,
    expression: Optional[str] = None,
) -> float:
    """Perform mathematical calculations safely.
    
    Can either perform an operation on two numbers ('a', 'b', 'operation') 
    or evaluate a safe math 'expression' (e.g., '125 * 48 / 5').
    """
    # 1. If an expression string is supplied
    if expression:
        clean_expr = expression.strip().replace("^", "**")
        try:
            parsed = ast.parse(clean_expr, mode="eval")
            return float(safe_eval_expr(parsed))
        except ZeroDivisionError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise ValueError(f"Failed to evaluate mathematical expression '{expression}': {str(e)}")

    # 2. Binary operations with a and b
    if a is None or b is None or operation is None:
        raise ValueError(
            "Calculator requires either 'expression' (e.g. '125 * 48') or "
            "'a', 'b', and 'operation' (e.g. a=125, b=48, operation='multiply')."
        )

    op = operation.strip().lower()
    if op in ("add", "+"):
        return float(a + b)
    elif op in ("subtract", "-"):
        return float(a - b)
    elif op in ("multiply", "*"):
        return float(a * b)
    elif op in ("divide", "/"):
        if b == 0:
            raise ValueError("Cannot divide by zero.")
        return float(a / b)
    elif op in ("power", "**"):
        return float(a ** b)
    elif op in ("modulo", "%"):
        if b == 0:
            raise ValueError("Cannot divide by zero.")
        return float(a % b)
    else:
        raise ValueError(
            f"Invalid operation '{operation}'. Supported operations: add, subtract, multiply, divide, power, modulo."
        )