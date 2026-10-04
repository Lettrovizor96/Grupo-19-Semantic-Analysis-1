# Projeto de Compiladores — Etapa 4: Análise Semântica 1

Este projeto implementa resolução de nomes, escopos e verificação de
tipos sobre a AST da MicroC. Leia o [enunciado completo](ENUNCIADO.pdf)
e mantenha por perto a especificação normativa da linguagem.

## Integração das etapas anteriores

`Lexer.py` foi integrado do projeto `Grupo-19`, e `parser.py`, do projeto
`Grupo-19-Parser`. A conversão de inteiros do lexer usa grupos de dígitos para
que literais muito longos também cheguem à verificação de limites na semântica.
Os arquivos `ast_nodes.py` e `ast_printer.py` são idênticos aos da etapa do
parser e preservam a interface publicada.

O pipeline mantém o mesmo objeto `Program` e seus nós:

```python
program = Parser(Lexer(source).scan()).parse()
program = SemanticAnalyzer().analyze(program)
```

A primeira passagem coleta assinaturas, cria escopos e vincula usos a símbolos.
A segunda verifica tipos e contextos. Erros de nomes impedem a passagem de
tipos. As anotações usam as chaves `symbol`, `scope` e `type` em `metadata`.

## Arquivos novos

- `symbols.py`: estruturas fundamentais de símbolos e escopos;
- `semantic_errors.py`: categorias e representação dos diagnósticos;
- `name_resolver.py`: passagem de resolução de nomes;
- `type_checker.py`: passagem de verificação de tipos;
- `semantic.py`: coordenação das duas passagens;
- `runner.py`: pipeline completo até a Análise Semântica 1;
- `tests/`: testes públicos e pequenos programas MicroC.

Os métodos e classes auxiliares usados internamente são escolha do grupo. Não
altere `symbols.py` nem `semantic_errors.py`: esses dois arquivos são contratos
fechados que serão reutilizados nas próximas etapas. Crie estruturas auxiliares
em outros módulos. As categorias de erro e chaves de metadados descritas no
enunciado também formam a interface da etapa.

## Ambiente e execução

O ambiente de referência usa Python 3.12.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python runner.py test.mc
python -m pytest -q
```

Os testes públicos verificam os contratos, metadados e diagnósticos do pipeline.
A correção também usa testes privados, sempre
compatíveis com o enunciado e com a especificação da MicroC.

## Limite desta etapa

Esta entrega valida nomes e tipos, inclusive chamadas, `main`, `return`
individual e limites dos literais. Ela ainda não verifica inicialização
definida, código inalcançável nem se toda função não-`void` retorna em todos os
caminhos. Esses problemas pertencem à Análise Semântica 2.

## Antes de entregar

- confirme a integração do lexer e do parser completos do grupo;
- execute todos os testes públicos;
- confira categorias e coordenadas dos diagnósticos;
- não antecipe a análise de fluxo da próxima etapa; e
- confira o último `push` no GitHub Actions.
