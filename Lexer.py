from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Iterator


class TokenKind(enum.Enum):
    """Classe já implementada: nomes e números não devem ser alterados."""

    EOF = -1

    IDENTIFIER = 1
    INT_LITERAL = 2
    STRING_LITERAL = 3

    KW_INT = 10
    KW_BOOL = 11
    KW_VOID = 12
    KW_TRUE = 13
    KW_FALSE = 14
    KW_IF = 15
    KW_ELSE = 16
    KW_WHILE = 17
    KW_RETURN = 18
    KW_PRINT = 19

    PLUS = 20
    MINUS = 21
    STAR = 22
    SLASH = 23
    PERCENT = 24
    LESS = 25
    LESS_EQUAL = 26
    GREATER = 27
    GREATER_EQUAL = 28
    EQUAL_EQUAL = 29
    NOT_EQUAL = 30
    LOGICAL_AND = 31
    LOGICAL_OR = 32
    LOGICAL_NOT = 33
    ASSIGN = 34

    LEFT_PAREN = 40
    RIGHT_PAREN = 41
    LEFT_BRACE = 42
    RIGHT_BRACE = 43
    COMMA = 44
    SEMICOLON = 45


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    lexeme: str
    value: int | str | bool | None
    line: int
    column: int

    def __str__(self) -> str:
        return (
            f"<{self.kind.value}, {self.kind.name}, {self.lexeme!r}, "
            f"{self.value!r}, {self.line}, {self.column}>"
        )


class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def __str__(self) -> str:
        return f"erro léxico em {self.line}:{self.column}: {self.message}"


class Lexer:
    """Converte texto-fonte MicroC em uma sequência de tokens."""

    def __init__(self, source: str):
        self.source = source
        self.index = 0
        self.line = 1
        self.column = 1

    def _peek(self, offset: int = 0) -> str:
        position = self.index + offset
        if position >= len(self.source) or position < 0:
            return ""
        return self.source[position]

    def _advance(self) -> str:
        character = self.source[self.index]
        self.index += 1
        if character == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return character

    def _skip_ignored(self) -> None:
        while True:
            while self._peek() in (" ", "\t", "\n"):
                self._advance()

            marker = self._peek() + self._peek(1)
            if marker not in ("//", "/*"):
                return

            comment_line, comment_column = self.line, self.column
            self._advance()
            self._advance()

            if marker == "//":
                while self.index < len(self.source) and self._peek() != "\n":
                    if ord(self._peek()) > 127:
                        raise LexerError("caractere nao ASCII", self.line, self.column)
                    self._advance()
                continue

            while self.index < len(self.source):
                character = self._peek()
                if ord(character) > 127:
                    raise LexerError("caractere nao ASCII", self.line, self.column)
                if character == "*" and self._peek(1) == "/":
                    self._advance()
                    self._advance()
                    break
                self._advance()
            else:
                raise LexerError("comentario de bloco nao terminado", comment_line, comment_column)

    @staticmethod
    def _is_identifier_start(character: str) -> bool:
        return (
            "A" <= character <= "Z"
            or "a" <= character <= "z"
            or character == "_"
        )

    @staticmethod
    def _is_identifier_part(character: str) -> bool:
        return Lexer._is_identifier_start(character) or "0" <= character <= "9"

    @staticmethod
    def _integer_value(lexeme: str) -> int:
        """Converte decimais sem depender do limite de dígitos do Python."""
        value = 0
        for offset in range(0, len(lexeme), 9):
            chunk = lexeme[offset:offset + 9]
            value = value * (10 ** len(chunk)) + int(chunk)
        return value

    def _read_string(self, start_line: int, start_column: int) -> Token:
        start = self.index
        self._advance()
        decoded: list[str] = []
        escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}

        while self.index < len(self.source):
            character = self._peek()
            if ord(character) > 127:
                raise LexerError("caractere nao ASCII", self.line, self.column)
            if character == '"':
                self._advance()
                return Token(
                    TokenKind.STRING_LITERAL,
                    self.source[start:self.index],
                    "".join(decoded),
                    start_line,
                    start_column,
                )
            if character == "\n":
                raise LexerError("quebra de linha em string", self.line, self.column)
            if character == "\\":
                escape_line, escape_column = self.line, self.column
                self._advance()
                if self.index >= len(self.source):
                    raise LexerError("string nao terminada", start_line, start_column)
                escaped = self._peek()
                if ord(escaped) > 127:
                    raise LexerError("caractere nao ASCII", self.line, self.column)
                if escaped == "\n":
                    raise LexerError("quebra de linha em string", self.line, self.column)
                if escaped not in escapes:
                    raise LexerError("escape invalido", escape_line, escape_column)
                decoded.append(escapes[escaped])
                self._advance()
            else:
                decoded.append(self._advance())

        raise LexerError("string nao terminada", start_line, start_column)

    def tokens(self) -> Iterator[Token]:
        """Produce tokens significativos e exatamente um EOF ao final."""
        self.index = 0
        self.line = 1
        self.column = 1

        keywords = {
            "int": TokenKind.KW_INT,
            "bool": TokenKind.KW_BOOL,
            "void": TokenKind.KW_VOID,
            "true": TokenKind.KW_TRUE,
            "false": TokenKind.KW_FALSE,
            "if": TokenKind.KW_IF,
            "else": TokenKind.KW_ELSE,
            "while": TokenKind.KW_WHILE,
            "return": TokenKind.KW_RETURN,
            "print": TokenKind.KW_PRINT,
        }
        two_character_operators = {
            "<=": TokenKind.LESS_EQUAL,
            ">=": TokenKind.GREATER_EQUAL,
            "==": TokenKind.EQUAL_EQUAL,
            "!=": TokenKind.NOT_EQUAL,
            "&&": TokenKind.LOGICAL_AND,
            "||": TokenKind.LOGICAL_OR,
        }
        one_character_tokens = {
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "*": TokenKind.STAR,
            "/": TokenKind.SLASH,
            "%": TokenKind.PERCENT,
            "<": TokenKind.LESS,
            ">": TokenKind.GREATER,
            "!": TokenKind.LOGICAL_NOT,
            "=": TokenKind.ASSIGN,
            "(": TokenKind.LEFT_PAREN,
            ")": TokenKind.RIGHT_PAREN,
            "{": TokenKind.LEFT_BRACE,
            "}": TokenKind.RIGHT_BRACE,
            ",": TokenKind.COMMA,
            ";": TokenKind.SEMICOLON,
        }

        while self.index < len(self.source):
            self._skip_ignored()
            if self.index >= len(self.source):
                break

            character = self._peek()
            start = self.index
            start_line, start_column = self.line, self.column
            if ord(character) > 127:
                raise LexerError("caractere nao ASCII", start_line, start_column)

            if character == '"':
                yield self._read_string(start_line, start_column)
                continue

            if self._is_identifier_start(character):
                self._advance()
                while self._is_identifier_part(self._peek()):
                    self._advance()
                lexeme = self.source[start:self.index]
                kind = keywords.get(lexeme, TokenKind.IDENTIFIER)
                if kind is TokenKind.KW_TRUE:
                    value: int | str | bool | None = True
                elif kind is TokenKind.KW_FALSE:
                    value = False
                elif kind is TokenKind.IDENTIFIER:
                    value = lexeme
                else:
                    value = None
                yield Token(kind, lexeme, value, start_line, start_column)
                continue

            if "0" <= character <= "9":
                self._advance()
                while "0" <= self._peek() <= "9":
                    self._advance()
                lexeme = self.source[start:self.index]
                yield Token(
                    TokenKind.INT_LITERAL,
                    lexeme,
                    self._integer_value(lexeme),
                    start_line,
                    start_column,
                )
                continue

            pair = character + self._peek(1)
            if pair in two_character_operators:
                self._advance()
                self._advance()
                yield Token(two_character_operators[pair], pair, None, start_line, start_column)
                continue

            if character in one_character_tokens:
                self._advance()
                yield Token(one_character_tokens[character], character, None, start_line, start_column)
                continue

            raise LexerError("caractere invalido", start_line, start_column)

        yield Token(TokenKind.EOF, "", None, self.line, self.column)

    def scan(self) -> list[Token]:
        return list(self.tokens())

