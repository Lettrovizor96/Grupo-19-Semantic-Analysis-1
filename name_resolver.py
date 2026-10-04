from __future__ import annotations

from dataclasses import fields, is_dataclass

from ast_nodes import (
    Assignment,
    BinaryExpr,
    Block,
    BoolLiteral,
    CallExpr,
    CallStmt,
    Expr,
    FunctionDecl,
    IdentifierExpr,
    IfStmt,
    IntLiteral,
    Parameter,
    PrintStmt,
    Program,
    ReturnStmt,
    Stmt,
    StringLiteral,
    TypeName,
    UnaryExpr,
    VarDecl,
    WhileStmt,
)
from semantic_errors import SemanticDiagnostic, SemanticError, SemanticErrorKind
from symbols import FunctionSymbol, Scope, Symbol, SymbolKind


class _NameResolver:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.functions: dict[str, FunctionSymbol] = {}
        self.diagnostics: list[SemanticDiagnostic] = []

    def run(self) -> None:
        self._clear_resolution_metadata(self.program)
        self._collect_functions()
        self._check_main()

        # Visit every declaration, including duplicate functions. Calls always
        # bind through the global table, which retains the first declaration.
        for function in self.program.functions:
            self._visit_function(function)

        if self.diagnostics:
            raise SemanticError(self.diagnostics)

    def _diagnose(self, kind: SemanticErrorKind, message: str, node: object) -> None:
        span = node.span  # type: ignore[attr-defined]
        self.diagnostics.append(SemanticDiagnostic(kind, message, span))

    def _clear_resolution_metadata(self, value: object) -> None:
        """Discard annotations from an earlier invocation on this same AST."""
        if isinstance(value, list):
            for item in value:
                self._clear_resolution_metadata(item)
            return
        if not is_dataclass(value):
            return
        metadata = getattr(value, "metadata", None)
        if isinstance(metadata, dict):
            metadata.pop("symbol", None)
            metadata.pop("scope", None)
        for item in fields(value):
            if item.name != "metadata":
                self._clear_resolution_metadata(getattr(value, item.name))

    def _collect_functions(self) -> None:
        for function in self.program.functions:
            symbol = FunctionSymbol(
                name=function.name,
                kind=SymbolKind.FUNCTION,
                type=function.return_type,
                declaration=function,
                parameter_types=tuple(parameter.type for parameter in function.parameters),
            )
            # Every declaration carries its own symbol metadata. Only the first
            # declaration occupies the global namespace and receives calls.
            function.metadata["symbol"] = symbol
            if function.name in self.functions:
                self._diagnose(
                    SemanticErrorKind.DUPLICATE_FUNCTION,
                    f"função '{function.name}' declarada mais de uma vez",
                    function,
                )
            else:
                self.functions[function.name] = symbol

    def _check_main(self) -> None:
        main = self.functions.get("main")
        if main is None:
            self._diagnose(
                SemanticErrorKind.INVALID_MAIN,
                "programa deve declarar int main()",
                self.program,
            )
        elif main.type is not TypeName.INT or main.parameter_types:
            self._diagnose(
                SemanticErrorKind.INVALID_MAIN,
                "a função main deve possuir assinatura int main()",
                main.declaration,
            )

    def _visit_function(self, function: FunctionDecl) -> None:
        outer = Scope(parent=None)
        function.body.metadata["scope"] = outer

        for parameter in function.parameters:
            symbol = Symbol(
                name=parameter.name,
                kind=SymbolKind.PARAMETER,
                type=parameter.type,
                declaration=parameter,
            )
            parameter.metadata["symbol"] = symbol
            self._declare(symbol, outer)

        self._visit_statements(function.body.statements, outer)

    def _visit_block(self, block: Block, parent: Scope) -> None:
        scope = Scope(parent=parent)
        block.metadata["scope"] = scope
        self._visit_statements(block.statements, scope)

    def _visit_statements(self, statements: list[Stmt], scope: Scope) -> None:
        for statement in statements:
            if isinstance(statement, VarDecl):
                symbol = Symbol(
                    name=statement.name,
                    kind=SymbolKind.VARIABLE,
                    type=statement.type,
                    declaration=statement,
                )
                statement.metadata["symbol"] = symbol
                # The declaration is visible in its own initializer.
                self._declare(symbol, scope)
                if statement.initializer is not None:
                    self._visit_expr(statement.initializer, scope)
            elif isinstance(statement, Assignment):
                self._visit_expr(statement.target, scope)
                self._visit_expr(statement.value, scope)
            elif isinstance(statement, CallStmt):
                self._visit_call(statement.call, scope)
            elif isinstance(statement, Block):
                self._visit_block(statement, scope)
            elif isinstance(statement, IfStmt):
                self._visit_expr(statement.condition, scope)
                self._visit_block(statement.then_block, scope)
                if statement.else_block is not None:
                    self._visit_block(statement.else_block, scope)
            elif isinstance(statement, WhileStmt):
                self._visit_expr(statement.condition, scope)
                self._visit_block(statement.body, scope)
            elif isinstance(statement, ReturnStmt):
                if statement.value is not None:
                    self._visit_expr(statement.value, scope)
            elif isinstance(statement, PrintStmt):
                for item in statement.items:
                    if isinstance(item, Expr):
                        self._visit_expr(item, scope)
                    elif isinstance(item, StringLiteral):
                        continue

    def _declare(self, symbol: Symbol, scope: Scope) -> None:
        if symbol.name in scope.symbols:
            self._diagnose(
                SemanticErrorKind.DUPLICATE_DECLARATION,
                f"'{symbol.name}' já foi declarado neste escopo",
                symbol.declaration,
            )
            return
        scope.symbols[symbol.name] = symbol

    def _lookup_variable(self, name: str, scope: Scope) -> Symbol | None:
        current: Scope | None = scope
        while current is not None:
            symbol = current.symbols.get(name)
            if symbol is not None:
                return symbol
            current = current.parent
        return None

    def _visit_expr(self, expression: Expr, scope: Scope) -> None:
        if isinstance(expression, IdentifierExpr):
            symbol = self._lookup_variable(expression.name, scope)
            if symbol is None:
                self._diagnose(
                    SemanticErrorKind.UNDECLARED_VARIABLE,
                    f"variável '{expression.name}' não declarada",
                    expression,
                )
            else:
                expression.metadata["symbol"] = symbol
        elif isinstance(expression, CallExpr):
            self._visit_call(expression, scope)
        elif isinstance(expression, UnaryExpr):
            self._visit_expr(expression.operand, scope)
        elif isinstance(expression, BinaryExpr):
            self._visit_expr(expression.left, scope)
            self._visit_expr(expression.right, scope)
        elif isinstance(expression, (IntLiteral, BoolLiteral)):
            return

    def _visit_call(self, call: CallExpr, scope: Scope) -> None:
        symbol = self.functions.get(call.name)
        if symbol is None:
            self._diagnose(
                SemanticErrorKind.UNDECLARED_FUNCTION,
                f"função '{call.name}' não declarada",
                call,
            )
        else:
            call.metadata["symbol"] = symbol
        # Arguments must still be resolved if the callee is unknown.
        for argument in call.arguments:
            self._visit_expr(argument, scope)


def resolve_names(program: Program) -> None:
    """Construa escopos, símbolos e vínculos entre usos e declarações."""
    _NameResolver(program).run()
