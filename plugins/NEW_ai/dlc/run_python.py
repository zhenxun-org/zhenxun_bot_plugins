import asyncio
import contextlib
import io

import openai

from zhenxun.services.log import logger

openai.api_key = ""  # api key支持openai协议的此处代码混乱需优化

openai.base_url = "https://api.siliconflow.cn/"  # "https://api.deepseek.com/"


class CodeExecutor:
    def __init__(self, max_code_executions=5):
        self.max_code_executions = max_code_executions
        self.code_execution_count = 0

    def _trim_multiline_comments(self, code: str) -> str:
        """删除代码字符串首尾的三引号"""
        code = code.strip()
        if (code.startswith('"""') and code.endswith('"""')) or (
            code.startswith("'''") and code.endswith("'''")
        ):
            code = code[3:-3]
        return code

    def execute_python_code(self, code: str) -> str:  # type: ignore
        """执行 Python 代码，并返回输出"""
        if self.code_execution_count >= self.max_code_executions:
            return "代码执行次数已达上限。"
        try:
            # remove multiline comments before execute
            code = self._trim_multiline_comments(code)
            with io.StringIO() as buffer, contextlib.redirect_stdout(buffer):
                exec(code, globals(), locals())
                output = buffer.getvalue()
            self.code_execution_count += 1
            text = f"代码执行结果:\n{output}"
            logger.info(text)
            return text
        except Exception as e:
            if openai.apikey:
                text = f"代码执行出错: {e}"
                logger.warning(text)
                asyncio.run(self.fix_bug(code=code, e=text))
            else:
                return f"代码执行出错: {e}"

    async def fix_bug(self, code, e):
        promote = """
"你是一个代码修复员你需要修复用户发送给你的代码，并直接回复修复后的代码。
 例子：代码:
 prin('hello world')
 出现问题:
 Traceback (most recent call last):
  File "d:\\python\\pycharm\\hello world.py", line 273, in <module>
    prin('hello world')
    ^^^^
NameError: name 'prin' is not defined. Did you mean: 'print'?
你需要直接给出修正的代码:print('hello world') 不需要添加任何多余的东西
        """
        message = [
            {"role": "system", "content": promote},
            {"role": "user", "content": f"代码:{code}出现问题{e}"},
        ]
        response = openai.chat.completions.create(  # 修改这里
            model="Pro/deepseek-ai/DeepSeek-R1",
            messages=message,  # type: ignore
            temperature=0,
        )
        self.execute_python_code(str(response))
