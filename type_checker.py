from __future__ import annotations

from dataclasses import fields

from ast_nodes import (
    Assignment,
    BinaryExpr,
    BinaryOperator,
    Block,
    BoolLiteral,
    CallExpr,
    CallStmt,
    Expr,
    IdentifierExpr,
    IfStmt,
    IntLiteral,
    Node,
    Parameter,
    PrintStmt,
    Program,
    ReturnStmt,
    TypeName,
    UnaryExpr,
    UnaryOperator,
    VarDecl,
    WhileStmt,
)
from semantic_errors import SemanticDiagnostic, SemanticError, SemanticErrorKind
from symbols import FunctionSymbol, Symbol


class _UnknownType:
    """Tipo interno usado para interromper cascatas de diagnósticos."""


_UNKNOWN = _UnknownType()
_INTEGER_MAX = 2**63 - 1


class _TypeChecker:
    def __init__(self) -> None:
        self.diagnostics: list[SemanticDiagnostic] = []
        self.return_type: TypeName | None = None

    def error(
        self,
        kind: SemanticErrorKind,
        node: Expr | ReturnStmt | Parameter | VarDecl,
        message: str,
    ) -> None:
        self.diagnostics.append(SemanticDiagnostic(kind, message, node.span))

    def run(self, program: Program) -> None:
        self.clear_types(program)
        for function in program.functions:
            symbol = function.metadata.get("symbol")
            self.return_type = symbol.type if isinstance(symbol, FunctionSymbol) else function.return_type
            for parameter in function.parameters:
                if parameter.type is TypeName.VOID:
                    self.error(
                        SemanticErrorKind.VOID_PARAMETER,
                        parameter,
                        f"o parâmetro {parameter.name!r} não pode ter tipo void",
                    )
            # O retorno de função é o contexto de todos os comandos do corpo.
            self.visit_block(function.body)
        self.return_type = None
        if self.diagnostics:
            raise SemanticError(self.diagnostics)

    def visit_block(self, block: Block) -> None:
        for statement in block.statements:
            if isinstance(statement, Block):
                self.visit_block(statement)
            elif isinstance(statement, VarDecl):
                self.visit_var_decl(statement)
            elif isinstance(statement, Assignment):
                self.visit_assignment(statement)
            elif isinstance(statement, CallStmt):
                self.visit_expr(statement.call, value_context=False)
            elif isinstance(statement, IfStmt):
                condition = self.visit_expr(statement.condition)
                self.require_condition(condition, statement.condition)
                self.visit_block(statement.then_block)
                if statement.else_block is not None:
                    self.visit_block(statement.else_block)
            elif isinstance(statement, WhileStmt):
                condition = self.visit_expr(statement.condition)
                self.require_condition(condition, statement.condition)
                self.visit_block(statement.body)
            elif isinstance(statement, ReturnStmt):
                self.visit_return(statement)
            elif isinstance(statement, PrintStmt):
                for item in statement.items:
                    if isinstance(item, Expr):
                        # Os únicos tipos imprimíveis são int e bool. Um void
                        # usado aqui já recebe VOID_VALUE_USED na chamada.
                        self.visit_expr(item)

    def visit_var_decl(self, declaration: VarDecl) -> None:
        symbol = declaration.metadata.get("symbol")
        declared_type = symbol.type if isinstance(symbol, Symbol) else declaration.type
        if declared_type is TypeName.VOID:
            self.error(
                SemanticErrorKind.VOID_VARIABLE,
                declaration,
                f"a variável {declaration.name!r} não pode ter tipo void",
            )
        if declaration.initializer is not None:
            initializer_type = self.visit_expr(declaration.initializer)
            expected = _UNKNOWN if declared_type is TypeName.VOID else declared_type
            if expected is not _UNKNOWN and initializer_type is not _UNKNOWN and initializer_type is not expected:
                self.error(
                    SemanticErrorKind.INITIALIZER_TYPE_MISMATCH,
                    declaration.initializer,
                    f"inicializador de {declaration.name!r} deve ter tipo {expected.value}",
                )

    def visit_assignment(self, assignment: Assignment) -> None:
        target_type = self.visit_identifier(assignment.target)
        value_type = self.visit_expr(assignment.value)
        if target_type is not _UNKNOWN and value_type is not _UNKNOWN and target_type is not value_type:
            self.error(
                SemanticErrorKind.ASSIGNMENT_TYPE_MISMATCH,
                assignment.value,
                "o valor atribuído deve ter o mesmo tipo da variável",
            )

    def visit_return(self, statement: ReturnStmt) -> None:
        expected = self.return_type
        if statement.value is None:
            if expected is not TypeName.VOID:
                self.diagnostics.append(
                    SemanticDiagnostic(
                        SemanticErrorKind.RETURN_MISMATCH,
                        "return sem expressão só é permitido em função void",
                        statement.span,
                    )
                )
            return

        actual = self.visit_expr(statement.value)
        if expected is TypeName.VOID:
            self.error(
                SemanticErrorKind.RETURN_MISMATCH,
                statement.value,
                "uma função void não pode retornar uma expressão",
            )
            return
        if actual is _UNKNOWN:
            return
        if expected is not None and actual is not expected:
            self.error(
                SemanticErrorKind.RETURN_MISMATCH,
                statement.value,
                "tipo da expressão retornada não corresponde ao retorno da função",
            )

    def require_condition(self, actual: TypeName | _UnknownType, expression: Expr) -> None:
        if actual is not _UNKNOWN and actual is not TypeName.BOOL:
            self.error(
                SemanticErrorKind.CONDITION_TYPE_MISMATCH,
                expression,
                "a condição deve ter tipo bool",
            )

    def visit_expr(self, expression: Expr, *, value_context: bool = True) -> TypeName | _UnknownType:
        if isinstance(expression, IntLiteral):
            if expression.value < 0 or expression.value > _INTEGER_MAX:
                self.error(
                    SemanticErrorKind.INTEGER_LITERAL_OUT_OF_RANGE,
                    expression,
                    "literal inteiro fora do intervalo permitido",
                )
                return _UNKNOWN
            return self.annotate(expression, TypeName.INT)

        if isinstance(expression, BoolLiteral):
            return self.annotate(expression, TypeName.BOOL)

        if isinstance(expression, IdentifierExpr):
            return self.visit_identifier(expression)

        if isinstance(expression, UnaryExpr):
            operand_type = self.visit_expr(expression.operand)
            required = TypeName.INT if expression.operator is UnaryOperator.NEGATE else TypeName.BOOL
            if operand_type is _UNKNOWN:
                return _UNKNOWN
            if operand_type is not required:
                self.error(
                    SemanticErrorKind.INVALID_UNARY_OPERAND,
                    expression,
                    f"o operador {expression.operator.value} exige operando {required.value}",
                )
                return _UNKNOWN
            return self.annotate(expression, required)

        if isinstance(expression, BinaryExpr):
            left_type = self.visit_expr(expression.left)
            right_type = self.visit_expr(expression.right)
            result_type = self.binary_result(expression.operator, left_type, right_type)
            if result_type is _UNKNOWN:
                if left_type is not _UNKNOWN and right_type is not _UNKNOWN:
                    self.error(
                        SemanticErrorKind.INVALID_BINARY_OPERANDS,
                        expression,
                        f"operandos incompatíveis para {expression.operator.value}",
                    )
                return _UNKNOWN
            return self.annotate(expression, result_type)

        if isinstance(expression, CallExpr):
            return self.visit_call(expression, value_context=value_context)

        return _UNKNOWN

    def visit_identifier(self, expression: IdentifierExpr) -> TypeName | _UnknownType:
        symbol = expression.metadata.get("symbol")
        if not isinstance(symbol, Symbol):
            return _UNKNOWN
        # Declarações void já são inválidas; tratá-las como desconhecidas evita
        # erros secundários em expressões que apenas dependem delas.
        declaration = symbol.declaration
        if symbol.type is TypeName.VOID and isinstance(declaration, (VarDecl, Parameter)):
            return _UNKNOWN
        return self.annotate(expression, symbol.type)

    def visit_call(self, expression: CallExpr, *, value_context: bool) -> TypeName | _UnknownType:
        symbol = expression.metadata.get("symbol")
        # A resolução interrompe a passagem de tipos se a função não existir.
        # Ainda assim, visitar argumentos deixa o visitante robusto ao uso isolado.
        argument_types = [self.visit_expr(argument) for argument in expression.arguments]
        if not isinstance(symbol, FunctionSymbol):
            return _UNKNOWN

        expected_types = symbol.parameter_types
        invalid_call = False
        if len(argument_types) != len(expected_types):
            invalid_call = True
            self.error(
                SemanticErrorKind.ARITY_MISMATCH,
                expression,
                f"a função {expression.name!r} espera {len(expected_types)} argumento(s)",
            )
        for argument, actual, expected in zip(expression.arguments, argument_types, expected_types):
            if expected is TypeName.VOID:
                # A assinatura já é inválida pela declaração do parâmetro;
                # não atribua incompatibilidade ao argumento em consequência.
                invalid_call = True
            elif actual is _UNKNOWN:
                invalid_call = True
            elif actual is not expected:
                invalid_call = True
                self.error(
                    SemanticErrorKind.ARGUMENT_TYPE_MISMATCH,
                    argument,
                    f"argumento deve ter tipo {expected.value}",
                )

        return_type = symbol.type
        if return_type is TypeName.VOID and value_context:
            self.error(
                SemanticErrorKind.VOID_VALUE_USED,
                expression,
                "uma chamada void não pode ser usada como valor",
            )
            self.annotate(expression, return_type)
            return _UNKNOWN
        if invalid_call:
            return _UNKNOWN
        return self.annotate(expression, return_type)

    @staticmethod
    def clear_types(node: Node) -> None:
        """Remove anotações de execução anterior antes de recalcular a AST."""
        if isinstance(node, Expr):
            node.metadata.pop("type", None)
        for item in fields(node):
            if item.name == "metadata":
                continue
            value = getattr(node, item.name)
            if isinstance(value, Node):
                _TypeChecker.clear_types(value)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, Node):
                        _TypeChecker.clear_types(child)

    @staticmethod
    def binary_result(
        operator: BinaryOperator,
        left: TypeName | _UnknownType,
        right: TypeName | _UnknownType,
    ) -> TypeName | _UnknownType:
        if left is _UNKNOWN or right is _UNKNOWN:
            return _UNKNOWN
        arithmetic = {
            BinaryOperator.ADD,
            BinaryOperator.SUBTRACT,
            BinaryOperator.MULTIPLY,
            BinaryOperator.DIVIDE,
            BinaryOperator.REMAINDER,
        }
        relational = {
            BinaryOperator.LESS,
            BinaryOperator.LESS_EQUAL,
            BinaryOperator.GREATER,
            BinaryOperator.GREATER_EQUAL,
        }
        if operator in arithmetic and left is TypeName.INT and right is TypeName.INT:
            return TypeName.INT
        if operator in relational and left is TypeName.INT and right is TypeName.INT:
            return TypeName.BOOL
        if operator in {BinaryOperator.EQUAL, BinaryOperator.NOT_EQUAL} and left is right and left in {TypeName.INT, TypeName.BOOL}:
            return TypeName.BOOL
        if operator in {BinaryOperator.LOGICAL_AND, BinaryOperator.LOGICAL_OR} and left is TypeName.BOOL and right is TypeName.BOOL:
            return TypeName.BOOL
        return _UNKNOWN

    @staticmethod
    def annotate(expression: Expr, type_name: TypeName) -> TypeName:
        expression.metadata["type"] = type_name
        return type_name


def check_types(program: Program) -> None:
    """Determine tipos de expressões e valide seus contextos."""

    _TypeChecker().run(program)
