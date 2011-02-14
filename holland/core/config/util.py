"""Config utility methods"""

import re

def unquote(value):
    """Remove quotes from a string

    This will both remove quotes at the start
    and end of a string and substitute any escaped
    characters with their real values.
    """
    escape_cre = re.compile(r'''\\(.)''')
    substitutions = {
        't' : "\t",
    }
    if len(value) and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    elif len(value) > 1 and value[0] == "'" and value[-1] == "'":
        value = value[1:-1]

    def substitute(match):
        char = match.group(1)
        # either replace with a substitution or
        # with the char itself \c => c if there is no substitution
        return substitutions.get(char, char)

    return escape_cre.sub(substitute, value)

class Missing(object):
    def __str__(self):
        return '<missing value>'
    __repr__ = __str__

missing = Missing()
del Missing
