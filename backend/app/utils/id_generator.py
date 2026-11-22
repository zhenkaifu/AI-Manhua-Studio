import uuid


def generate_id(prefix: str) -> str:
    """生成稳定的全局唯一 ID，例如 character_3f9a1b2c4d5e。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
