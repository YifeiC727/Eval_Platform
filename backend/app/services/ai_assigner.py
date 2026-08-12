import os
import json
import httpx

ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://modelservice.jdcloud.com/anthropic")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "pk-0f965c3e-2133-4976-9a77-9910de9f20f0")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-hq")


def parse_assignment_instruction(instruction: str, annotators: list[dict], total_videos: int) -> dict:
    """
    调用 Claude API 解析自然语言分配指令，返回每人应分配的题目数量。

    annotators: [{"id": 1, "name": "张三", "current_tasks": 5}, ...]
    total_videos: 待分配的视频总数

    返回: {"allocations": [{"id": 1, "name": "张三", "count": 50}, ...], "reasoning": "..."}
    """
    annotator_desc = "\n".join(
        f"  - ID={a['id']}, 姓名={a['name']}, 当前已有任务数={a['current_tasks']}"
        for a in annotators
    )

    system_prompt = """你是一个评测任务分配助手。用户会给出自然语言的分配指令，你需要根据指令计算每个标注员应分配多少题目。

规则：
1. 所有标注员分配的题目总数必须等于待分配总数
2. 如果用户没有明确指定某些人的数量，剩余题目在剩余人中均匀分配
3. 如果指令不明确，默认均匀分配
4. 返回严格的JSON格式"""

    user_prompt = f"""待分配视频总数: {total_videos}
可用标注员:
{annotator_desc}

用户分配指令: "{instruction}"

请根据指令计算每人应分配的题目数量。返回严格JSON格式:
{{
  "allocations": [
    {{"id": <标注员ID>, "name": "<姓名>", "count": <分配数量>}}
  ],
  "reasoning": "<简短解释你的分配逻辑>"
}}

注意：所有人的count之和必须等于{total_videos}。只返回JSON，不要其他内容。"""

    headers = {
        "x-api-key": ANTHROPIC_AUTH_TOKEN,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": user_prompt}
        ],
        "system": system_prompt,
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{ANTHROPIC_BASE_URL}/v1/messages",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["content"][0]["text"]
        # 提取 JSON（兼容 markdown code block）
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())

        # 校验总数
        total_allocated = sum(a["count"] for a in result["allocations"])
        if total_allocated != total_videos:
            diff = total_videos - total_allocated
            result["allocations"][-1]["count"] += diff
            result["reasoning"] += f" (已自动修正差额{diff}题)"

        return result

    except Exception as e:
        # fallback: 均匀分配
        n = len(annotators)
        base = total_videos // n
        remainder = total_videos % n
        allocations = []
        for i, a in enumerate(annotators):
            count = base + (1 if i < remainder else 0)
            allocations.append({"id": a["id"], "name": a["name"], "count": count})
        return {
            "allocations": allocations,
            "reasoning": f"AI调用失败({str(e)})，已回退为均匀分配",
        }
