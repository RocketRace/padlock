# -*- coding: utf-8 -*-

'''
The MIT License (MIT)

Copyright (c) 2020 RocketRace

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
'''

import logging

from collections import namedtuple
from enum        import Enum
from typing      import List, Iterable

log = logging.getLogger("padlock")

# Exceptions
class PadlockException(Exception):
    '''
    Base exception for all Padlock exceptions
    '''
    pass

class InvalidSymbol(PadlockException):
    '''
    Raised when the parser encounters an unexpected Padlock symbol.
    '''
    pass

class InvalidArgumentCount(PadlockException):
    '''
    Raised when an instruction received the wrong amount of name arguments.
    '''
    pass

class UnexpectedEOF(PadlockException):
    '''
    Raised when a program unexpectedly reaches EOF.
    '''
    pass

# Default emoji symbols
class Symbol(Enum):
    lock    = "\N{LOCK}"
    unlock  = "\N{OPEN LOCK}"
    key     = "\N{KEY}"
    pen     = "\N{LOWER LEFT FOUNTAIN PEN}"
    keylock = "\N{CLOSED LOCK WITH KEY}"
    penlock = "\N{LOCK WITH INK PEN}"

# Instructions
Instruction = namedtuple("Instruction", ("name", "symbol", "args", "processes"))
nil     = Instruction("nil"    , Symbol.lock,    0, 0)
split   = Instruction("split"  , Symbol.unlock,  0, 2)
decrypt = Instruction("decrypt", Symbol.key,     2, 1)
name    = Instruction("name"   , Symbol.pen,     1, 1)
send    = Instruction("send"   , Symbol.keylock, 2, 1)
receive = Instruction("receive", Symbol.penlock, 2, 1)
instructions = (nil, split, decrypt, name, send, receive)

class AST:
    '''
    The AST object containing Padlock source code.
    '''
    def __init__(self):
        self.instructions = []

    def __repr__(self):
        return "<Padlock AST object>"

    def __str__(self):
        return self._parse_line(self.instructions)

    def _parse_line(self, line, *, depth = 0):
        '''
        Recursively convert AST instructions to string
        '''
        out = []
        for item in line:
            if isinstance(item, Instruction):
                out.append(item.symbol.value + " ")
            elif isinstance(item, str):
                out.append(f"'{item}' ")
            else:
                out.append("\n" + "  " * (depth + 1))
                out.append(self._parse_line(item, depth=depth + 1))

        return "".join(out)

    def push(self, value, indices=[]):
        '''
        Traverses the AST to a given depth and appends a value.
        '''
        x = self.instructions
        for i in indices:
            x = x[i]
        x.append(value)

def parse(stream: str, *, utf8_names: bool = False, ascii_symbols: bool = False) -> AST:
    '''
    Parses a stream of Padlock symbols into an AST.

    # Paramaters

    `utf8_names`: Whether or not non-Padlock symbols should be allowed within names.
    Defaults to False.

    `ascii_symbols`: Whether or not an alternate character set should be used.
    Defaults to False.
    '''

    # ASCII replacement characters
    if ascii_symbols:
        lock    = "N" # Nil
        unlock  = "S" # Split
        key     = "K" # Key
        pen     = "P" # Pen
        keylock = "E" # Encrypt
        penlock = "R" # Receive
    else:
        # Emoji characters
        lock    = "\N{LOCK}"
        unlock  = "\N{OPEN LOCK}"
        key     = "\N{KEY}"
        pen     = "\N{LOWER LEFT FOUNTAIN PEN}"
        keylock = "\N{CLOSED LOCK WITH KEY}"
        penlock = "\N{LOCK WITH INK PEN}"

    symbols = (lock, unlock, key, pen, keylock, penlock)

    # Parser states
    idle  = 0 # Waiting for an instruction
    raw   = 1 # In the middle of a name
    blank = 2 # Not waiting for any more input

    # Initial state
    state = idle
    ast = AST()
    stack_ptr = []
    instruction = nil
    name_count = 0
    name_stack = []

    log.info(f"Trying to parse the program")
    for i, char in enumerate(stream):
        log.debug(f"Parsing character '{char}' in position {i} in state {state}...")
        # Expect an instruction identifier
        if state == idle:
            # Valid instruction symbol
            try:
                index = symbols.index(char)
                # Push instruction
                instruction = instructions[index]
                ast.push(instruction, stack_ptr)
                name_count = 0
                if instruction == nil:
                    # Escape from current AST branch
                    try:
                        log.debug(f"Escaping from current program branch, at position {i})")
                        while stack_ptr[-1] == -1:
                            stack_ptr.pop()
                    # Program is over
                    except IndexError:
                        log.info(f"Reached end of program at position {i}")
                        state = blank
                    # Enter parallel branch
                    else:
                        log.debug(f"Entering second branch of split instruction, at position {i}")
                        stack_ptr[-1] = -1
                # Add new paths to AST
                elif instruction == split:
                    log.debug(f"Branching at position {i}")
                    ast.push([], stack_ptr)
                    ast.push([], stack_ptr)
                    stack_ptr.append(-2)
                else:
                    log.debug(f"Parsing names in position {i}")
                    state = raw
            except ValueError:
                log.info(f"Ignoring invalid character '{char}' within program body, position {i}")
        # Parse contents of name literally (raw)
        elif state == raw:
            # Delimiter
            if char == pen:
                name_count += 1
                if instruction.args > name_count:
                    current_name = "".join(name_stack)
                    log.debug(f"Pushing name '{current_name}' to AST, position {i}")
                    ast.push(current_name, stack_ptr)
                    name_stack.clear()
                elif instruction.args == name_count:
                    current_name = "".join(name_stack)
                    log.debug(f"Pushing final name '{current_name}' to AST, position {i}")
                    ast.push(current_name, stack_ptr)
                    name_stack.clear()
                    state = idle
                else:
                    raise InvalidArgumentCount(f"{instruction.name} expects {instruction.args} name arguments, got {name_count}")
            else:
                # Names can contain any characters, or only Padlock ones
                # This depends on the `utf8_names` argument
                if (utf8_names and not char.isspace()) or char in symbols:
                    log.debug(f"Pushing character '{char}' to name stack, position {i}")
                    name_stack.append(char)
                else:
                    log.info(f"Ignoring invalid character '{char}' within name, position {i}")
        # Do not expect any more program characters
        elif state == blank:
            if char in symbols:
                raise InvalidSymbol(f"Got unexpected character '{char}' in position {i} after the end of the program")
            else:
                log.info(f"Ignoring invalid character '{char}' after program body, position {i}")

    if state == idle:
        raise UnexpectedEOF(f"Unexpected EOF while waiting for an instruction")
    if state == raw:
        raise UnexpectedEOF(f"Unexpected EOF while parsing names")

    return ast

# Syntax:
# Lock (nil)
# Pen _ Pen . (create name) 
# Unlock . . (execute in parallel)
# Key _ Pen _ Pen . (decrypt _ into _ and replicate)
# Keylock _ Pen _ Pen . (encrypt _ and send to _)
# Penlock _ Pen _ Pen . (receive from _ and bind to _)