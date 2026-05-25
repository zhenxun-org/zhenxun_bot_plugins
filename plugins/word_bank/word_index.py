from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
import re
from typing import Any, ClassVar

from tortoise.expressions import Q

from zhenxun.services.log import logger

from ._config import ScopeType, WordType

_ENTRY_FIELDS = (
    "id",
    "user_id",
    "group_id",
    "word_scope",
    "word_type",
    "problem",
    "answer",
    "placeholder",
    "image_path",
    "platform",
    "author",
)
_ACTIVE_ENTRY_Q = Q(status=True) | Q(status__isnull=True)


@dataclass(slots=True)
class WordBankEntry:
    id: int
    problem: str
    answer: str
    placeholder: str | None
    word_type: int
    word_scope: int
    group_id: str | None
    user_id: str
    image_path: str | None = None
    platform: str | None = None
    author: str | None = None
    compiled_pattern: re.Pattern[str] | None = field(default=None, repr=False)


@dataclass(slots=True)
class WordBankShard:
    exact: dict[str, list[WordBankEntry]] = field(default_factory=dict)
    image: dict[str, list[WordBankEntry]] = field(default_factory=dict)
    fuzzy: list[WordBankEntry] = field(default_factory=list)
    regex: list[WordBankEntry] = field(default_factory=list)

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> "WordBankShard":
        shard = cls()
        for row in rows:
            entry = WordBankEntry(
                id=int(row["id"]),
                problem=str(row.get("problem") or ""),
                answer=str(row.get("answer") or ""),
                placeholder=row.get("placeholder"),
                word_type=int(row.get("word_type") or WordType.EXACT.value),
                word_scope=int(row.get("word_scope") or ScopeType.GLOBAL.value),
                group_id=(
                    str(row["group_id"])
                    if row.get("group_id") is not None
                    else None
                ),
                user_id=str(row.get("user_id") or ""),
                image_path=row.get("image_path"),
                platform=row.get("platform"),
                author=row.get("author"),
            )
            if entry.word_type == WordType.EXACT.value:
                shard.exact.setdefault(entry.problem, []).append(entry)
            elif entry.word_type == WordType.IMAGE.value:
                shard.image.setdefault(entry.problem, []).append(entry)
            elif entry.word_type == WordType.FUZZY.value:
                shard.fuzzy.append(entry)
            elif entry.word_type == WordType.REGEX.value:
                try:
                    entry.compiled_pattern = re.compile(entry.problem)
                except re.error as e:
                    logger.warning(
                        f"跳过非法正则词条 id={entry.id}: {entry.problem}",
                        "词库索引",
                        e=e,
                    )
                    continue
                shard.regex.append(entry)
        return shard

    def match_exact_or_image(
        self,
        problem: str,
        word_type: WordType | None = None,
    ) -> list[WordBankEntry]:
        result: list[WordBankEntry] = []
        if word_type in (None, WordType.EXACT):
            result.extend(self.exact.get(problem, ()))
        if word_type in (None, WordType.IMAGE):
            result.extend(self.image.get(problem, ()))
        return result

    def match_fuzzy(
        self,
        problem: str,
        word_type: WordType | None = None,
    ) -> list[WordBankEntry]:
        if word_type not in (None, WordType.FUZZY):
            return []
        return [entry for entry in self.fuzzy if entry.problem in problem]

    def match_regex(
        self,
        problem: str,
        word_type: WordType | None = None,
    ) -> list[WordBankEntry]:
        if word_type not in (None, WordType.REGEX):
            return []
        return [
            entry
            for entry in self.regex
            if entry.compiled_pattern and entry.compiled_pattern.search(problem)
        ]


class WordBankIndex:
    _max_group_shards: ClassVar[int] = 128
    _global_shard: ClassVar[WordBankShard | None] = None
    _private_shard: ClassVar[WordBankShard | None] = None
    _group_shards: ClassVar[OrderedDict[str, WordBankShard]] = OrderedDict()
    _locks: ClassVar[dict[tuple[str, str], asyncio.Lock]] = {}

    @classmethod
    async def preload_global(cls, model_cls: type[Any]) -> None:
        await cls._get_global_shard(model_cls)

    @classmethod
    async def match(
        cls,
        model_cls: type[Any],
        group_id: str | None,
        problem: str,
        word_scope: ScopeType | None = None,
        word_type: WordType | None = None,
    ) -> list[WordBankEntry]:
        shards = await cls._get_candidate_shards(model_cls, group_id, word_scope)
        exact_or_image: list[WordBankEntry] = []
        for shard in shards:
            exact_or_image.extend(shard.match_exact_or_image(problem, word_type))
        if exact_or_image:
            return exact_or_image

        fuzzy: list[WordBankEntry] = []
        for shard in shards:
            fuzzy.extend(shard.match_fuzzy(problem, word_type))
        if fuzzy:
            return fuzzy

        regex: list[WordBankEntry] = []
        for shard in shards:
            regex.extend(shard.match_regex(problem, word_type))
        return regex

    @classmethod
    def invalidate_scope(
        cls,
        word_scope: ScopeType | None = None,
        group_id: str | None = None,
    ) -> None:
        if word_scope is None:
            cls._global_shard = None
            cls._private_shard = None
            cls._group_shards.clear()
            return
        if word_scope == ScopeType.GLOBAL:
            cls._global_shard = None
        elif word_scope == ScopeType.PRIVATE:
            cls._private_shard = None
        elif word_scope == ScopeType.GROUP:
            if group_id:
                group_key = str(group_id)
                cls._group_shards.pop(group_key, None)
                cls._locks.pop(("group", group_key), None)
            else:
                cls._group_shards.clear()
                cls._locks = {
                    key: lock
                    for key, lock in cls._locks.items()
                    if key[0] != "group"
                }

    @classmethod
    async def _get_candidate_shards(
        cls,
        model_cls: type[Any],
        group_id: str | None,
        word_scope: ScopeType | None,
    ) -> list[WordBankShard]:
        if word_scope == ScopeType.GLOBAL:
            return [await cls._get_global_shard(model_cls)]
        if word_scope == ScopeType.PRIVATE:
            return [await cls._get_private_shard(model_cls)]
        if word_scope == ScopeType.GROUP:
            return [await cls._get_group_shard(model_cls, group_id)] if group_id else []
        if group_id:
            return [
                await cls._get_group_shard(model_cls, group_id),
                await cls._get_global_shard(model_cls),
            ]
        return [
            await cls._get_private_shard(model_cls),
            await cls._get_global_shard(model_cls),
        ]

    @classmethod
    async def _get_global_shard(cls, model_cls: type[Any]) -> WordBankShard:
        if cls._global_shard is not None:
            return cls._global_shard
        async with cls._get_lock("global", ""):
            if cls._global_shard is None:
                cls._global_shard = await cls._load_shard(
                    model_cls,
                    ScopeType.GLOBAL,
                    None,
                )
        return cls._global_shard

    @classmethod
    async def _get_private_shard(cls, model_cls: type[Any]) -> WordBankShard:
        if cls._private_shard is not None:
            return cls._private_shard
        async with cls._get_lock("private", ""):
            if cls._private_shard is None:
                cls._private_shard = await cls._load_shard(
                    model_cls,
                    ScopeType.PRIVATE,
                    None,
                )
        return cls._private_shard

    @classmethod
    async def _get_group_shard(
        cls,
        model_cls: type[Any],
        group_id: str | None,
    ) -> WordBankShard:
        group_key = str(group_id or "")
        if not group_key:
            return WordBankShard()
        if shard := cls._group_shards.get(group_key):
            cls._group_shards.move_to_end(group_key)
            return shard
        async with cls._get_lock("group", group_key):
            if shard := cls._group_shards.get(group_key):
                cls._group_shards.move_to_end(group_key)
                return shard
            shard = await cls._load_shard(model_cls, ScopeType.GROUP, group_key)
            cls._group_shards[group_key] = shard
            cls._group_shards.move_to_end(group_key)
            while len(cls._group_shards) > cls._max_group_shards:
                old_key, _ = cls._group_shards.popitem(last=False)
                cls._locks.pop(("group", old_key), None)
            return shard

    @classmethod
    async def _load_shard(
        cls,
        model_cls: type[Any],
        word_scope: ScopeType,
        group_id: str | None,
    ) -> WordBankShard:
        query = model_cls.filter(_ACTIVE_ENTRY_Q, word_scope=word_scope.value)
        if word_scope == ScopeType.GROUP:
            query = query.filter(group_id=group_id)
        rows = await query.values(*_ENTRY_FIELDS)
        return WordBankShard.from_rows(list(rows))

    @classmethod
    def _get_lock(cls, scope: str, key: str) -> asyncio.Lock:
        lock_key = (scope, key)
        if lock_key not in cls._locks:
            cls._locks[lock_key] = asyncio.Lock()
        return cls._locks[lock_key]
