from datetime import datetime
from enum import IntEnum, unique
from typing import TYPE_CHECKING

from objects import glob

if TYPE_CHECKING:
    from objects.player import Player

__all__ = ('Clan', 'ClanPrivileges')


@unique
class ClanPrivileges(IntEnum):
    """A class to represent a clan members privs."""
    Member = 1
    Officer = 2
    Owner = 3

#! TODO: MUST FIX THIS DAMN CLANS BEFORE PUSH


class Clan:
    """A class to represent a single gulag clan."""
    __slots__ = ('id', 'name', 'tag', 'created_at',
                 'owner', 'members')

    def __init__(self, _id: int, name: str, tag: str,
                 created_at: datetime, owner: int,
                 members: set[int] = set()) -> None:
        """A class representing one of gulag's clans."""
        self.id = _id
        self.name = name
        self.tag = tag
        self.created_at = created_at

        self.owner = owner  # userid
        self.members = members  # userids

    async def add_member(self, p: 'Player') -> None:
        """Add a given player to the clan's members."""
        self.members.add(p.id)

        glob.db.execute(
            'UPDATE users '
            'SET clan_id = %s, clan_priv = 1 '
            'WHERE id = %s',
            [self.id, p.id]
        )

        glob.db.users.update_one(
            {'id': p.id},
            {'$set': {'clan_id': self.id, 'clan_priv': 1}}
        )

        p.clan = self
        p.clan_priv = ClanPrivileges.Member

    async def remove_member(self, p: 'Player') -> None:
        """Remove a given player from the clan's members."""
        self.members.remove(p.id)

        async with glob.db.pool.acquire() as conn:
            async with conn.cursor() as db_cursor:
                await db_cursor.execute(
                    'UPDATE users '
                    'SET clan_id = 0, clan_priv = 0 '
                    'WHERE id = %s',
                    [p.id]
                )

                if not self.members:
                    # no members left, disband clan.
                    await db_cursor.execute(
                        'DELETE FROM clans '
                        'WHERE id = %s',
                        [self.id]
                    )
                elif p.id == self.owner:
                    # owner leaving and members left,
                    # transfer the ownership.
                    # TODO: prefer officers
                    self.owner = next(iter(self.members))

                    await db_cursor.execute(
                        'UPDATE clans '
                        'SET owner = %s '
                        'WHERE id = %s',
                        [self.owner, self.id]
                    )

                    await db_cursor.execute(
                        'UPDATE users '
                        'SET clan_priv = 3 '
                        'WHERE id = %s',
                        [self.owner]
                    )

        p.clan = None
        p.clan_priv = None
