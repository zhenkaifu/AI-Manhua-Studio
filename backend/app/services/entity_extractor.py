from app.services.ollama_service import chat_json

EXTRACT_PROMPT = """你是一名专业的中文漫剧制片助理。你的任务是从中文小说片段中提取所有「明确出场的角色」和「明确出现的场景」。

规则：
1. 只提取小说原文明确提到的信息，不要编造。小说没有提供的外貌、年龄等字段留空字符串。
2. 每个角色和场景都要给出 evidence 字段，复制小说原文中支持你判断的句子片段。
3. confidence 是你对这条提取的自我评估，0 到 1 之间。
4. visual_prompt 用英文撰写，只描述角色的确定外观信息，不写任何画风，项目画风会在生成时统一添加。
5. 只输出合法JSON，不要输出Markdown，不要输出任何解释。

JSON 结构严格如下：
{
  "characters": [
    {
      "name": "角色名字",
      "aliases": ["别名"],
      "age_description": "",
      "appearance": "外貌描述",
      "hairstyle": "",
      "clothing": "",
      "personality": "",
      "visual_prompt": "English visual prompt",
      "confidence": 0.95,
      "evidence": "原文句子"
    }
  ],
  "scenes": [
    {
      "name": "场景名称",
      "aliases": [],
      "location_type": "indoor 或 outdoor",
      "environment": "环境描述",
      "architecture": "",
      "lighting": "",
      "atmosphere": "",
      "visual_prompt": "English visual prompt",
      "confidence": 0.9,
      "evidence": "原文句子"
    }
  ]
}

如果小说中没有明确的角色或场景，对应数组返回空数组。"""


async def extract_entities(novel: str) -> dict:
    """用配置的 LLM 从小说提取角色和场景，返回 {"characters": [...], "scenes": [...]}。"""
    result = await chat_json(
        EXTRACT_PROMPT,
        "请从以下小说片段中提取角色和场景：\n\n" + novel,
    )
    result.setdefault("characters", [])
    result.setdefault("scenes", [])
    return result
