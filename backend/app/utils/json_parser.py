import json
import re


def parse_ai_json(text: str) -> dict:
    """从模型输出中稳健地解析 JSON：容忍 Markdown 代码块和前后多余文字。"""
    text = text.strip()

    # 去掉 ```json ... ``` 代码围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试截取第一个 { 到最后一个 } 之间的内容
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise
