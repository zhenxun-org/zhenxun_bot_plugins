from inspect import Parameter, signature
from typing import ClassVar
import uuid

import nonebot
from nonebot import get_loaded_plugins
from nonebot.utils import is_coroutine_callable
import ujson as json

from zhenxun.configs.utils import AICallableTag, PluginExtraData
from zhenxun.services.log import logger

from .config import FunctionParam, Tool, base_config

driver = nonebot.get_driver()


class AiCallTool:
    tools: ClassVar[dict[str, AICallableTag]] = {}

    @classmethod
    def load_tool(cls):
        """加载可用的工具"""
        loaded_plugins = get_loaded_plugins()

        for plugin in loaded_plugins:
            if not plugin or not plugin.metadata or not plugin.metadata.extra:
                continue
            extra_data = PluginExtraData(**plugin.metadata.extra)
            if extra_data.smart_tools:
                for tool in extra_data.smart_tools:
                    if tool.name in cls.tools:
                        raise ValueError(f"Ai智能工具工具名称重复: {tool.name}")
                    cls.tools[tool.name] = tool

    @classmethod
    async def build_conversation(
        cls,
        tool_calls: list[Tool],
        func_param: FunctionParam,
    ) -> str:
        """构建聊天记录

        参数:
            bot: Bot
            event: Event
            tool_calls: 工具
            func_param: 函数参数

        返回:
            list[ChatMessage]: 聊天列表
        """
        temp_conversation = []
        # 去重，避免函数多次调用
        tool_calls = list({tool.function.name: tool for tool in tool_calls}.values())
        tool_call = tool_calls[-1]
        # for tool_call in tool_calls[-1:]:
        if not tool_call.id:
            tool_call.id = str(uuid.uuid4())
        func = tool_call.function
        tool = cls.tools.get(func.name)
        tool_result = ""
        if tool and tool.func:
            func_sign = signature(tool.func)

            parsed_args = func_param.to_dict()
            if args := func.arguments:
                parsed_args.update(json.loads(args))

            func_params = {
                key: parsed_args[key]
                for key, param in func_sign.parameters.items()
                if param.kind
                in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
                and key in parsed_args
            }
            try:
                if is_coroutine_callable(tool.func):
                    tool_result = await tool.func(**func_params)
                else:
                    tool_result = tool.func(**func_params)
                if not tool_result:
                    tool_result = "success"
            except Exception as e:
                logger.error(f"调用Ai智能工具 {func.name}", "BYM_AI", e=e)
                tool_result = str(e)
            # temp_conversation.append(
            #     ChatMessage(
            #         role="tool",
            #         tool_call_id=tool_call.id,
            #         content=tool_result,
            #     )
            # )
        return tool_result


@driver.on_startup
def _():
    if base_config.get("BYM_AI_CHAT_SMART"):
        AiCallTool.load_tool()
        logger.info(
            f"加载Ai智能工具完成, 成功加载 {len(AiCallTool.tools)} 个AI智能工具"
        )
