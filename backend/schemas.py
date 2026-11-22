from pydantic import BaseModel, Field
from typing import List


class Character(BaseModel):
    id: str = Field(..., description="角色唯一ID，例如 char_01")
    name: str = Field(..., description="角色姓名")
    appearance: str = Field(..., description="角色外观描述，供图片生成参考")
    personality: str = Field(..., description="角色性格")
    role: str = Field(..., description="角色定位，例如 主角/反派/配角")


class Shot(BaseModel):
    id: int = Field(..., description="镜头编号，从1开始")
    duration: int = Field(..., description="镜头时长，单位秒，4-10秒")
    scene: str = Field(..., description="场景描述")
    camera: str = Field(..., description="景别/运镜，例如 wide shot, medium shot, close-up, low angle")
    characters: List[str] = Field(..., description="出场角色ID列表")
    action: str = Field(..., description="镜头内动作描述")
    dialogue: str = Field(..., description="对白，无对白则为空字符串")
    visual_prompt: str = Field(..., description="供图片生成模型使用的视觉提示词")


class Episode(BaseModel):
    episode: int = Field(..., description="集数")
    title: str = Field(..., description="本集标题")
    summary: str = Field(..., description="本集剧情简介")
    characters: List[Character]
    shots: List[Shot]
