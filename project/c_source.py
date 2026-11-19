"""C lexical primitives for flight templates, the editor and the ground packet catalog."""
import re


_LEXEME = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\\n])*"|\'(?:\\[\s\S]|[^\'\\\n])*\'')


def comments(text):
    """Yield C comment tokens with original offsets, skipping string and character literals."""
    return (match for match in _LEXEME.finditer(text) if match[0].startswith('/'))


def blank_lexemes(text, literals=True):
    """Blank comments, and literals unless kept, without moving offsets or lines."""
    def blank(match):
        if not literals and match[0][0] in '"\'':
            return match[0]
        return re.sub(r'[^\n]', ' ', match[0])
    return _LEXEME.sub(blank, text)


def closing(text, opening, left='(', right=')'):
    """Offset of the delimiter that closes text[opening], or None when unbalanced."""
    depth = 1
    for position in range(opening + 1, len(text)):
        if text[position] == left:
            depth += 1
        elif text[position] == right:
            depth -= 1
            if not depth:
                return position
    return None
