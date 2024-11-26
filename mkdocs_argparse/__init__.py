import importlib
import re
from typing import Callable, Iterable, Iterator
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
import argparse
import json
import mistune

__all__ = ["MKArgparseExtension", "MkDocsArgparseException", "makeExtension"]


def makeExtension() -> Extension:
    return MKArgparseExtension()


class MkDocsArgparseException(Exception):
    pass


class MKArgparseExtension(Extension):
    def extendMarkdown(self, md: any) -> None:
        md.registerExtension(self)
        processor = ArgparseProcessor(md.parser)
        md.preprocessors.register(processor, "mk_argparse", 142)


class ArgparseProcessor(Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        return list(
            replace_blocks(lines, title="mkdocs-argparse", replace=replace_parser_docs)
        )


def load_parser(module: str, attribute: str) -> argparse.ArgumentParser:
    function = _load_obj(module, attribute)

    if not isinstance(parser := function(), argparse.ArgumentParser):
        raise MkDocsArgparseException(
            f"{attribute!r} must be an 'argparse.ArgumentParser' object, got {type(parser)}"
        )

    return parser


def _load_obj(module: str, attribute: str) -> any:
    try:
        mod = importlib.import_module(module)
    except SystemExit:
        raise MkDocsArgparseException("the module appeared to call sys.exit()")

    try:
        return getattr(mod, attribute)
    except AttributeError:
        raise MkDocsArgparseException(
            f"Module {module!r} has no attribute {attribute!r}"
        )


def replace_parser_docs(**options: any) -> Iterator[str]:
    for option in ("module", "function"):
        if option not in options:
            raise MkDocsArgparseException(f"Option {option!r} is required")

    module = options["module"]
    function = options["function"]
    depth = int(options.get("depth", 0))

    return make_parser_docs(load_parser(module, function), level=depth)


def make_parser_docs(parser: argparse.ArgumentParser, level: int = 0) -> Iterator[str]:
    yield "#" * (level + 1) + " " + parser.prog
    yield ""

    if description := parser.description:
        yield from description.splitlines()
        yield ""

    yield "Usage:"
    yield ""
    yield "```"
    yield parser.format_usage().removeprefix("usage: ")
    yield "```"

    optional, positional = [], []

    for action in parser._actions:
        if action.dest == "help":
            continue

        if action.default and not action.required:
            action.help += " (default: %(default))"

        action.help = action.help.replace("%(default)", json.dumps(action.default))

        if action.option_strings:
            optional += [action]
        else:
            positional += [action]

    if optional:
        yield ""
        yield "Options:"
        yield ""
    for action in optional:
        name = " / ".join(f"`{option}`" for option in action.option_strings)
        yield f"* {name} — {mistune.escape(action.help)}"

    if positional:
        yield ""
        yield "Arguments:"
        yield ""
    for action in positional:
        name = action.metavar or action.dest
        yield f"* `{name}` — {mistune.escape(action.help)}"

    yield ""

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for parser in sorted(
                action.choices.values(), key=lambda parser: parser.prog
            ):
                yield from make_parser_docs(parser, level=level + 1)


def replace_blocks(
    lines: Iterable[str], title: str, replace: Callable[..., Iterable[str]]
) -> Iterator[str]:
    options = {}
    in_block_section = False

    for line in lines:
        if in_block_section:
            match = re.search(r"^\s+:(?P<key>.+):(?:\s+(?P<value>\S+))?", line)
            if match is not None:
                key = match.group("key")
                value = match.group("value") or ""
                options[key] = value
                continue

            in_block_section = False
            yield from replace(**options)
            yield line
            continue

        match = re.search(rf"^::: {title}", line)
        if match is not None:
            in_block_section = True
            options = {}
        else:
            yield line
