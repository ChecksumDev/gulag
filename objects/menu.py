# note that this is still a very rough draft of
# the concept and is subject to major refactoring
import random
from enum import IntEnum, unique
from typing import (TYPE_CHECKING, Awaitable, Callable, NamedTuple, Optional,
                    Union)

from objects import glob

if TYPE_CHECKING:
    from objects.player import Player


@unique
class MenuCommands(IntEnum):
    Reset = 0  # go to main menu
    Back = 1  # go to previous menu
    Advance = 2  # go to new menu
    Execute = 3  # execute a function on current menu


class Menu(NamedTuple):
    name: str
    options: 'dict[int, tuple[MenuCommands, Optional[Union[Menu, MenuFunction]]]]'


class MenuFunction(NamedTuple):
    name: str
    callback: Callable[['Player'], Awaitable[None]]


def menu_keygen() -> int:
    min_key = glob.config.max_multi_matches
    return random.randint(min_key, 0x7fffffff)
