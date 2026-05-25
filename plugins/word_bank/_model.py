from datetime import datetime
import random
import re
import time
from typing import Any, ClassVar, NamedTuple
from typing_extensions import Self
import uuid

from nonebot_plugin_alconna import At, AtAll, Image, Text, UniMessage
from tortoise import Tortoise, fields
from tortoise.expressions import Q

from zhenxun.configs.config import BotConfig
from zhenxun.configs.path_config import DATA_PATH
from zhenxun.services.db_context import Model
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.image_utils import get_img_hash
from zhenxun.utils.message import MessageUtils

from ._config import ScopeType, WordType, int2type
from .exception import ImageDownloadError
from .word_index import WordBankEntry, WordBankIndex

path = DATA_PATH / "word_bank"
_NEGATIVE_CACHE_TTL_SECONDS = 45.0
_NEGATIVE_CACHE_MAX_SIZE = 4096
DEFAULT_PROBLEM_PAGE_SIZE = 50


class WordBankProblemRow(NamedTuple):
    problem: Any | str
    word_type: str
    author: str


class WordBank(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255)
    """用户id"""
    group_id = fields.CharField(255, null=True)
    """群聊id"""
    word_scope = fields.IntField(default=ScopeType.GLOBAL.value)
    """生效范围 0: 全局 1: 群聊 2: 私聊"""
    word_type = fields.IntField(default=WordType.EXACT.value)
    """词条类型 0: 完全匹配 1: 模糊 2: 正则 3: 图片"""
    status = fields.BooleanField()
    """词条状态"""
    problem = fields.TextField()
    """问题，为图片时使用图片hash"""
    answer = fields.TextField()
    """回答"""
    placeholder = fields.TextField(null=True)
    """占位符"""
    image_path = fields.TextField(null=True)
    """使用图片作为问题时图片存储的路径"""
    to_me = fields.CharField(255, null=True)
    """昵称开头时存储的昵称"""
    create_time = fields.DatetimeField(auto_now=True)
    """创建时间"""
    update_time = fields.DatetimeField(auto_now_add=True)
    """更新时间"""
    platform = fields.CharField(255, default="qq")
    """平台"""
    author = fields.CharField(255, null=True, default="")
    """收录人"""

    class Meta:  # type: ignore
        table = "word_bank2"
        table_description = "词条数据库"

    _negative_match_cache: ClassVar[dict[tuple[str, str], float]] = {}
    _index_ready: ClassVar[bool] = False

    @classmethod
    def _match_cache_key(cls, group_id: str | None, problem: str) -> tuple[str, str]:
        return str(group_id or ""), str(problem or "")

    @classmethod
    def _negative_cache_hit(cls, group_id: str | None, problem: str) -> bool:
        key = cls._match_cache_key(group_id, problem)
        expire_at = cls._negative_match_cache.get(key)
        if expire_at is None:
            return False
        if expire_at <= time.monotonic():
            cls._negative_match_cache.pop(key, None)
            return False
        return True

    @classmethod
    def _remember_negative_match(cls, group_id: str | None, problem: str) -> None:
        if len(cls._negative_match_cache) >= _NEGATIVE_CACHE_MAX_SIZE:
            now = time.monotonic()
            expired = [
                key
                for key, expire_at in cls._negative_match_cache.items()
                if expire_at <= now
            ]
            for key in expired:
                cls._negative_match_cache.pop(key, None)
            if len(cls._negative_match_cache) >= _NEGATIVE_CACHE_MAX_SIZE:
                cls._negative_match_cache.pop(next(iter(cls._negative_match_cache)))
        cls._negative_match_cache[cls._match_cache_key(group_id, problem)] = (
            time.monotonic() + _NEGATIVE_CACHE_TTL_SECONDS
        )

    @classmethod
    def clear_match_cache(cls, problem: str | None = None) -> None:
        if problem is None:
            cls._negative_match_cache.clear()
            return
        problem = str(problem or "")
        for key in list(cls._negative_match_cache):
            if key[1] == problem:
                cls._negative_match_cache.pop(key, None)

    @classmethod
    def invalidate_match_index(
        cls,
        word_scope: ScopeType | None = None,
        group_id: str | None = None,
        problem: str | None = None,
    ) -> None:
        cls.clear_match_cache(problem)
        WordBankIndex.invalidate_scope(word_scope, group_id)

    @classmethod
    async def ensure_query_indexes(cls) -> None:
        if cls._index_ready:
            return
        db_type = BotConfig.get_sql_type()
        db = Tortoise.get_connection("default")
        if "mysql" in db_type:
            scripts = [
                (
                    "CREATE INDEX idx_word_bank_scope_type_problem "
                    "ON word_bank2(word_scope, word_type, problem(191));"
                ),
                (
                    "CREATE INDEX idx_word_bank_group_type_problem "
                    "ON word_bank2(group_id, word_type, problem(191));"
                ),
                (
                    "CREATE INDEX idx_word_bank_group_scope_type_problem "
                    "ON word_bank2(group_id, word_scope, word_type, problem(191));"
                ),
            ]
        else:
            scripts = [
                (
                    "CREATE INDEX IF NOT EXISTS idx_word_bank_scope_type_problem "
                    "ON word_bank2(word_scope, word_type, problem);"
                ),
                (
                    "CREATE INDEX IF NOT EXISTS idx_word_bank_group_type_problem "
                    "ON word_bank2(group_id, word_type, problem);"
                ),
                (
                    "CREATE INDEX IF NOT EXISTS "
                    "idx_word_bank_group_scope_type_problem "
                    "ON word_bank2(group_id, word_scope, word_type, problem);"
                ),
            ]
        for sql in scripts:
            try:
                await db.execute_script(sql)
            except Exception:
                if "mysql" not in db_type:
                    raise
        cls._index_ready = True

    @classmethod
    async def exists(  # type: ignore
        cls,
        user_id: str | None,
        group_id: str | None,
        problem: str,
        answer: str | None,
        word_scope: ScopeType | None = None,
        word_type: WordType | None = None,
    ) -> bool:
        """检测问题是否存在

        参数:
            user_id: 用户id
            group_id: 群号
            problem: 问题
            answer: 回答
            word_scope: 词条范围
            word_type: 词条类型
        """
        query = cls.filter(problem=problem)
        if user_id:
            query = query.filter(user_id=user_id)
        if group_id:
            query = query.filter(group_id=group_id)
        if answer:
            query = query.filter(answer=answer)
        if word_type is not None:
            query = query.filter(word_type=word_type.value)
        if word_scope is not None:
            query = query.filter(word_scope=word_scope.value)
        return await query.exists()

    @classmethod
    async def add_problem_answer(
        cls,
        user_id: str,
        group_id: str | None,
        word_scope: ScopeType,
        word_type: WordType,
        problem: str,
        answer: list[str | Text | At | Image],
        to_me_nickname: str | None = None,
        platform: str = "",
        author: str = "",
    ):
        """添加或新增一个问答

        参数:
            user_id: 用户id
            group_id: 群号
            word_scope: 词条范围,
            word_type: 词条类型,
            problem: 问题, 为图片时是URl
            answer: 回答
            to_me_nickname: at真寻名称
            platform: 所属平台
            author: 收录人id
        """
        # 对图片做额外处理
        image_path = None
        if word_type == WordType.IMAGE:
            _uuid = uuid.uuid1()
            _file = path / "problem" / f"{group_id}" / f"{user_id}_{_uuid}.jpg"
            _file.parent.mkdir(exist_ok=True, parents=True)
            if not await AsyncHttpx.download_file(problem, _file):
                raise ImageDownloadError()
            problem = get_img_hash(_file)
            image_path = f"problem/{group_id}/{user_id}_{_uuid}.jpg"
        new_answer, placeholder_list = await cls._answer2format(
            answer,  # type: ignore
            user_id,
            group_id,
        )
        if not await cls.exists(
            user_id, group_id, problem, new_answer, word_scope, word_type
        ):
            await cls.create(
                user_id=user_id,
                group_id=group_id,
                word_scope=word_scope.value,
                word_type=word_type.value,
                status=True,
                problem=str(problem).strip(),
                answer=new_answer,
                image_path=image_path,
                placeholder=",".join(placeholder_list),
                create_time=datetime.now().replace(microsecond=0),
                update_time=datetime.now().replace(microsecond=0),
                to_me=to_me_nickname,
                platform=platform,
                author=author,
            )
            cls.invalidate_match_index(word_scope, group_id, str(problem).strip())

    @classmethod
    async def _answer2format(
        cls,
        answer: list[str | Text | At | AtAll | Image],
        user_id: str,
        group_id: str | None,
    ) -> tuple[str, list[Any]]:
        """将特殊字段转化为占位符，图片，at等

        参数:
            answer: 回答内容
            user_id: 用户id
            group_id: 群号

        返回:
            tuple[str, list[Any]]: 替换后的文本回答内容，占位符
        """
        placeholder_list = []
        text = ""
        index = 0
        for seg in answer:
            placeholder = uuid.uuid1()
            if isinstance(seg, str):
                text += seg
            elif isinstance(seg, Text):
                text += seg.text
            elif seg.type == "face":  # TODO: face貌似无用...
                text += f"[face:placeholder_{placeholder}]"
                placeholder_list.append(seg.data["id"])
            elif isinstance(seg, At | AtAll):
                text += f"[at:placeholder_{placeholder}]"
                placeholder_list.append(seg.target if isinstance(seg, At) else "0")
            elif isinstance(seg, Image) and seg.url:
                text += f"[image:placeholder_{placeholder}]"
                index += 1
                _file = (
                    path
                    / "answer"
                    / f"{group_id or user_id}"
                    / f"{user_id}_{placeholder}.jpg"
                )
                _file.parent.mkdir(exist_ok=True, parents=True)
                if not await AsyncHttpx.download_file(seg.url, _file):
                    raise ImageDownloadError()
                placeholder_list.append(
                    f"answer/{group_id or user_id}/{user_id}_{placeholder}.jpg"
                )
        return text, placeholder_list

    @classmethod
    async def _format2answer(
        cls,
        problem: str,
        answer: str,
        user_id: str | int,
        group_id: str | int | None,
        query: Any | None = None,
    ) -> UniMessage:
        """将占位符转换为实际内容

        参数:
            problem: 问题内容
            answer: 回答内容
            user_id: 用户id
            group_id: 群组id
        """
        if not query:
            query = await cls.get_or_none(
                problem=problem,
                user_id=user_id,
                group_id=group_id,
                answer=answer,
            )
        if not answer:
            answer = str(query.answer)  # type: ignore
        if query and query.placeholder:
            type_list = re.findall(r"\[(.*?):placeholder_.*?]", answer)
            answer_split = re.split(r"\[.*?:placeholder_.*?]", answer)
            placeholder_split = query.placeholder.split(",")
            result_list = []
            for index, ans in enumerate(answer_split):
                result_list.append(ans)
                if index < len(type_list):
                    t = type_list[index]
                    p = placeholder_split[index]
                    if t == "at":
                        if p == "0":
                            result_list.append(AtAll())
                        else:
                            result_list.append(At(flag="user", target=p))
                    elif t == "image":
                        result_list.append(path / p)
            return MessageUtils.build_message(result_list)
        return MessageUtils.build_message(answer)

    @classmethod
    async def check_problem(
        cls,
        group_id: str | None,
        problem: str,
        word_scope: ScopeType | None = None,
        word_type: WordType | None = None,
    ) -> Any:
        """检测是否包含该问题并获取所有回答"""

        query = cls.filter(Q(status=True) | Q(status__isnull=True))
        if group_id:
            if word_scope:
                query = query.filter(word_scope=word_scope.value)
            else:
                query = query.filter(
                    Q(group_id=group_id) | Q(word_scope=ScopeType.GLOBAL.value)
                )
        else:
            query = query.filter(
                Q(word_scope=ScopeType.PRIVATE.value)
                | Q(word_scope=ScopeType.GLOBAL.value)
            )
            if word_type:
                query = query.filter(word_type=word_type.value)

        # 完全匹配
        if data_list := await query.filter(
            Q(Q(word_type=WordType.EXACT.value) | Q(word_type=WordType.IMAGE.value)),
            Q(problem=problem),
        ).all():
            return data_list
        db = Tortoise.get_connection("default")
        db_class_name = BotConfig.get_sql_type()
        # 模糊匹配：处理 POSITION 和 INSTR 的差异
        if "postgres" in db_class_name:
            sql = (
                query.filter(word_type=WordType.FUZZY.value).sql()
                + " AND POSITION(problem IN $1) > 0"
            )
            params = [problem]
        elif "sqlite" in db_class_name:
            sql = (
                query.filter(word_type=WordType.FUZZY.value).sql()
                + " AND INSTR(?, problem) > 0"
            )
            params = [problem]
        elif "mysql" in db_class_name:
            sql = (
                query.filter(word_type=WordType.FUZZY.value).sql()
                + " AND INSTR(%s, problem) > 0"
            )
            params = [problem]
        else:
            raise Exception(f"Unsupported database type: {db_class_name}")

        data_list = await db.execute_query_dict(sql, params)
        if data_list:
            return [cls(**data) for data in data_list]

        # 正则匹配
        if "postgres" in db_class_name:
            sql = (
                query.filter(word_type=WordType.REGEX.value, word_scope__not=999).sql()
                + " AND $1 ~ problem"
            )
            params = [problem]
        elif "sqlite" in db_class_name:
            # SQLite 不支持 REGEXP，使用 LIKE 替代
            sql = (
                query.filter(word_type=WordType.REGEX.value, word_scope__not=999).sql()
                + " AND problem LIKE ?"
            )
            params = [f"%{problem}%"]
        elif "mysql" in db_class_name:
            sql = (
                query.filter(word_type=WordType.REGEX.value, word_scope__not=999).sql()
                + " AND problem REGEXP ?"
            )
            params = [problem]

        data_list = await db.execute_query_dict(sql, params)
        return [cls(**data) for data in data_list] if data_list else None

    @classmethod
    async def match_entry(
        cls,
        group_id: str | None,
        problem: str,
        word_scope: ScopeType | None = None,
        word_type: WordType | None = None,
    ) -> Self | WordBankEntry | None:
        """获取一条已匹配词条；未命中会短 TTL 缓存，避免闲聊反复查库。"""
        if not problem:
            return None
        if cls._negative_cache_hit(group_id, problem):
            return None
        try:
            data_list = await WordBankIndex.match(
                cls,
                group_id,
                problem,
                word_scope,
                word_type,
            )
        except Exception:
            data_list = await cls.check_problem(
                group_id,
                problem,
                word_scope,
                word_type,
            )
        if not data_list:
            cls._remember_negative_match(group_id, problem)
            return None
        return random.choice(data_list)

    @classmethod
    async def format_entry_answer(
        cls,
        entry: Self | WordBankEntry,
        problem: str,
    ) -> UniMessage:
        answer = entry.answer
        if entry.word_type == WordType.REGEX.value:
            r = re.search(entry.problem, problem)
            has_placeholder = re.search(r"\$(\d)", answer)
            if r and r.groups() and has_placeholder:
                pats = re.sub(r"\$(\d)", r"\\\1", answer)
                answer = re.sub(entry.problem, pats, problem)
        return (
            await cls._format2answer(
                entry.problem,
                answer,
                entry.user_id,
                entry.group_id,
                entry,
            )
            if entry.placeholder
            else MessageUtils.build_message(answer)
        )

    @classmethod
    async def get_answer(
        cls,
        group_id: str | None,
        problem: str,
        word_scope: ScopeType | None = None,
        word_type: WordType | None = None,
    ) -> UniMessage | None:
        """根据问题内容获取随机回答

        参数:
            user_id: 用户id
            group_id: 群组id
            problem: 问题内容
            word_scope: 词条范围
            word_type: 词条类型
        """
        if entry := await cls.match_entry(group_id, problem, word_scope, word_type):
            return await cls.format_entry_answer(entry, problem)

    @classmethod
    async def get_problem_all_answer(
        cls,
        problem: str,
        index: int | None = None,
        group_id: str | None = None,
        word_scope: ScopeType | None = ScopeType.GLOBAL,
    ) -> tuple[str, list[UniMessage]]:
        """获取指定问题所有回答

        参数:
            problem: 问题
            index: 下标
            group_id: 群号
            word_scope: 词条范围

        返回:
            tuple[str, list[UniMessage]]: 问题和所有回答
        """
        if index is not None:
            indexed_problem = await cls.get_problem_by_index(
                index,
                group_id,
                word_scope or ScopeType.GLOBAL,
            )
            if indexed_problem is None:
                return "下标错误，必须小于问题数量...", []
            problem = indexed_problem
        f = cls.filter(
            problem=problem, word_scope=(word_scope or ScopeType.GLOBAL).value
        )
        if group_id and word_scope != ScopeType.GLOBAL:
            f = f.filter(group_id=group_id)
        answer_list = await f.all()
        if not answer_list:
            return "词条不存在...", []
        return problem, [await cls._format2answer("", "", 0, 0, a) for a in answer_list]

    @classmethod
    async def delete_group_problem(
        cls,
        problem: str,
        group_id: str | None,
        index: int | None = None,
        word_scope: ScopeType = ScopeType.GROUP,
    ):
        """删除指定问题全部或指定回答

        参数:
            problem: 问题文本
            group_id: 群号
            index: 回答下标
            word_scope: 词条范围
        """
        if await cls.exists(None, group_id, problem, None, word_scope):
            if index is not None:
                if group_id:
                    query = await cls.filter(
                        group_id=group_id, problem=problem, word_scope=word_scope.value
                    ).all()
                else:
                    query = await cls.filter(
                        word_scope=word_scope.value, problem=problem
                    ).all()
                await query[index].delete()
            else:
                if group_id:
                    await WordBank.filter(
                        group_id=group_id, problem=problem, word_scope=word_scope.value
                    ).delete()
                else:
                    await WordBank.filter(
                        word_scope=word_scope.value, problem=problem
                    ).delete()
            cls.clear_match_cache(problem)
            cls.invalidate_match_index(word_scope, group_id, problem)
            return True
        return False

    @classmethod
    async def update_group_problem(
        cls,
        problem: str,
        replace_str: str,
        group_id: str | None,
        index: int | None = None,
        word_scope: ScopeType = ScopeType.GROUP,
    ) -> str:
        """修改词条问题

        参数:
            problem: 问题
            replace_str: 替换问题
            group_id: 群号
            index: 问题下标
            word_scope: 词条范围

        返回:
            str: 修改前的问题
        """
        if index is not None:
            if group_id:
                query = await cls.filter(group_id=group_id, problem=problem).all()
            else:
                query = await cls.filter(
                    word_scope=word_scope.value, problem=problem
                ).all()
            tmp = query[index].problem
            query[index].problem = replace_str
            await query[index].save(update_fields=["problem"])
            cls.invalidate_match_index(word_scope, group_id, tmp)
            cls.clear_match_cache(replace_str)
            return tmp
        else:
            if group_id:
                await cls.filter(group_id=group_id, problem=problem).update(
                    problem=replace_str
                )
            else:
                await cls.filter(word_scope=word_scope.value, problem=problem).update(
                    problem=replace_str
                )
            cls.invalidate_match_index(word_scope, group_id, problem)
            cls.clear_match_cache(replace_str)
            return problem

    @classmethod
    async def get_group_all_problem(
        cls,
        group_id: str,
        page: int = 1,
        page_size: int = DEFAULT_PROBLEM_PAGE_SIZE,
    ) -> list[WordBankProblemRow]:
        """获取群聊所有词条

        参数:
            group_id: 群号
        """
        return await cls.get_problem_page(
            group_id=group_id,
            word_scope=ScopeType.GROUP,
            page=page,
            page_size=page_size,
        )

    @classmethod
    async def get_problem_by_scope(
        cls,
        word_scope: ScopeType,
        page: int = 1,
        page_size: int = DEFAULT_PROBLEM_PAGE_SIZE,
    ) -> list[WordBankProblemRow]:
        """通过词条范围获取词条

        参数:
            word_scope: 词条范围
        """
        return await cls.get_problem_page(
            word_scope=word_scope,
            page=page,
            page_size=page_size,
        )

    @classmethod
    async def get_problem_by_type(
        cls,
        word_type: int,
        page: int = 1,
        page_size: int = DEFAULT_PROBLEM_PAGE_SIZE,
    ) -> list[WordBankProblemRow]:
        """通过词条类型获取词条

        参数:
            word_type: 词条类型
        """
        return cls._handle_problem_rows(
            await cls.filter(word_type=word_type)
            .distinct()
            .order_by("problem", "word_type", "image_path")
            .offset(cls._page_offset(page, page_size))
            .limit(page_size)
            .values_list("problem", "word_type", "image_path")
        )

    @classmethod
    async def get_problem_page(
        cls,
        group_id: str | None = None,
        word_scope: ScopeType = ScopeType.GLOBAL,
        page: int = 1,
        page_size: int = DEFAULT_PROBLEM_PAGE_SIZE,
    ) -> list[WordBankProblemRow]:
        query = cls._problem_list_query(group_id, word_scope)
        return cls._handle_problem_rows(
            await query.distinct()
            .order_by("problem", "word_type", "image_path")
            .offset(cls._page_offset(page, page_size))
            .limit(page_size)
            .values_list("problem", "word_type", "image_path")
        )

    @classmethod
    async def count_problem_page(
        cls,
        group_id: str | None = None,
        word_scope: ScopeType = ScopeType.GLOBAL,
    ) -> int:
        db_type = BotConfig.get_sql_type()
        db = Tortoise.get_connection("default")
        params: list[Any] = []

        def placeholder() -> str:
            params.append(None)
            if "postgres" in db_type:
                return f"${len(params)}"
            if "mysql" in db_type:
                return "%s"
            return "?"

        if group_id and word_scope != ScopeType.GLOBAL:
            group_placeholder = placeholder()
            scope_placeholder = placeholder()
            params[-2:] = [group_id, word_scope.value]
            where_sql = (
                f"group_id = {group_placeholder} "
                f"AND word_scope = {scope_placeholder}"
            )
        else:
            scope_placeholder = placeholder()
            params[-1] = word_scope.value
            where_sql = f"word_scope = {scope_placeholder}"

        sql = (
            "SELECT COUNT(*) AS count FROM ("
            "SELECT DISTINCT problem, word_type, image_path "
            f"FROM word_bank2 WHERE {where_sql}"
            ") AS word_bank_count"
        )
        rows = await db.execute_query_dict(sql, params)
        return int(next(iter(rows[0].values()))) if rows else 0

    @classmethod
    async def get_problem_by_index(
        cls,
        index: int,
        group_id: str | None = None,
        word_scope: ScopeType = ScopeType.GLOBAL,
    ) -> str | None:
        rows: list[tuple[Any, ...]] = (
            await cls._problem_list_query(group_id, word_scope)
            .distinct()
            .order_by("problem", "word_type", "image_path")
            .offset(index)
            .limit(1)
            .values_list("problem", "word_type", "image_path")
        )
        return str(rows[0][0]) if rows else None

    @classmethod
    def _problem_list_query(
        cls,
        group_id: str | None = None,
        word_scope: ScopeType = ScopeType.GLOBAL,
    ):
        if group_id and word_scope != ScopeType.GLOBAL:
            return cls.filter(group_id=group_id, word_scope=word_scope.value)
        return cls.filter(word_scope=word_scope.value)

    @classmethod
    def _page_offset(cls, page: int, page_size: int) -> int:
        return max(page - 1, 0) * page_size

    @classmethod
    def __type2int(cls, value: int) -> str:
        for key, member in WordType.__members__.items():
            if member.value == value:
                return key
        return ""

    @classmethod
    def _handle_problem_rows(
        cls,
        problem_list: list[tuple[str, int, str | None]],
    ) -> list[WordBankProblemRow]:
        """格式化处理问题

        参数:
            msg_list: 消息列表
        """
        result_list = []
        for problem, word_type_value, image_path in problem_list:
            word_type = cls.__type2int(word_type_value)
            result_list.append(
                WordBankProblemRow(
                    (path / image_path, 30, 30) if image_path else problem,
                    int2type[word_type],
                    "-",
                )
            )
        return result_list

    @classmethod
    async def _move(
        cls,
        user_id: str,
        group_id: str | None,
        problem: str,
        answer: str,
        placeholder: str,
    ):
        """旧词条图片移动方法

        参数:
            user_id: 用户id
            group_id: 群号
            problem: 问题
            answer: 回答
            placeholder: 占位符
        """
        word_scope = ScopeType.GLOBAL
        word_type = WordType.EXACT
        # 对图片做额外处理
        if not await cls.exists(
            user_id, group_id, problem, answer, word_scope, word_type
        ):
            await cls.create(
                user_id=user_id,
                group_id=group_id,
                word_scope=word_scope.value,
                word_type=word_type.value,
                status=True,
                problem=problem,
                answer=answer,
                image_path=None,
                placeholder=placeholder,
                create_time=datetime.now().replace(microsecond=0),
                update_time=datetime.now().replace(microsecond=0),
            )
            cls.invalidate_match_index(word_scope, group_id, problem)

    @classmethod
    async def _run_script(cls):
        return [
            "ALTER TABLE word_bank2 ADD to_me varchar(255);",  # 添加 to_me 字段
            (
                "ALTER TABLE word_bank2 ALTER COLUMN create_time TYPE timestamp"
                " with time zone USING create_time::timestamp with time zone;"
            ),
            (
                "ALTER TABLE word_bank2 ALTER COLUMN update_time TYPE timestamp"
                " with time zone USING update_time::timestamp with time zone;"
            ),
            "ALTER TABLE word_bank2 RENAME COLUMN user_qq TO user_id;",
            # 将user_qq改为user_id
            "ALTER TABLE word_bank2 ALTER COLUMN user_id TYPE character varying(255);",
            "ALTER TABLE word_bank2 ALTER COLUMN group_id TYPE character varying(255);",
            "ALTER TABLE word_bank2 ADD platform varchar(255) DEFAULT 'qq';",
            "ALTER TABLE word_bank2 ADD author varchar(255) DEFAULT '';",
        ]
