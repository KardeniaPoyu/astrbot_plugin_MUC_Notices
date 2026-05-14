from astrbot.api.event import AstrMessageEvent

from rss_service import Notice


def extract_command_args(event: AstrMessageEvent, command_name: str) -> str:
    command_name = command_name.lower()
    for candidate in event_text_candidates(event):
        normalized = " ".join(candidate.strip().split())
        if not normalized:
            continue

        lowered = normalized.lower()
        prefixes = [
            f"/muc_notice {command_name}",
            f"muc_notice {command_name}",
            f"{command_name}",
        ]
        for prefix in prefixes:
            if lowered == prefix:
                return ""
            if lowered.startswith(prefix + " "):
                return normalized[len(prefix) :].strip()

        if "muc_notice" not in lowered and command_name not in lowered:
            return normalized
    return ""


def event_text_candidates(event: AstrMessageEvent) -> list[str]:
    candidates: list[str] = []
    for attr in ("message_str", "message_text", "raw_message", "text"):
        value = getattr(event, attr, None)
        if isinstance(value, str) and value.strip():
            candidates.append(value)

    message_obj = getattr(event, "message_obj", None)
    if message_obj is not None:
        for attr in ("message_str", "text"):
            value = getattr(message_obj, attr, None)
            if isinstance(value, str) and value.strip():
                candidates.append(value)

    return candidates


def format_latest_lines(title: str, notices: list[Notice]) -> str:
    lines = [title]
    for item in notices:
        lines.append(f"- [{item['source']}] {item['date']} | {item['title']}")
        lines.append(item["link"])
    return "\n".join(lines)
