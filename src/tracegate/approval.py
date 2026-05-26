import sys
import asyncio
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def prompt_for_approval(
    tool_name: str,
    arguments: Dict[str, Any],
    message: str,
    timeout: int = 60,
    risk_level: Optional[str] = None,
) -> str:
    """
    Prompt the user for approval via /dev/tty.

    Opens /dev/tty directly to avoid corrupting the MCP stdio streams.
    Falls back to secure denial if /dev/tty is unavailable (CI, Docker, SSH).
    """
    # Format prompt
    risk_str = f"  Risk: {risk_level.upper()}\n" if risk_level else ""
    args_str = json.dumps(arguments, indent=2, default=str)
    if len(args_str) > 500:
        args_str = args_str[:500] + "\n  ... (truncated)"

    prompt_text = (
        f"\n{'='*60}\n"
        f"  ⚠️  TraceGate: Approval Required\n"
        f"{'='*60}\n"
        f"  Tool:    {tool_name}\n"
        f"{risk_str}"
        f"  Reason:  {message}\n"
        f"  Args:\n{_indent(args_str, 4)}\n"
        f"  Allow this action? [y/N/always/never]: "
    )

    try:
        with open('/dev/tty', 'r+') as tty:
            loop = asyncio.get_running_loop()

            def _write():
                tty.write(prompt_text)
                tty.flush()

            def _read():
                return tty.readline().strip().lower()

            await loop.run_in_executor(None, _write)

            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, _read),
                    timeout=timeout,
                )
                if response in ('always', 'a'):
                    tty.write("  ✅ Approved (Always for this session)\n\n")
                    return 'always'
                elif response in ('never', 'n', 'no'):
                    tty.write("  ❌ Denied (Never for this session)\n\n")
                    return 'never'
                elif response in ('y', 'yes'):
                    tty.write("  ✅ Approved\n\n")
                    return 'yes'
                else:
                    tty.write("  ❌ Denied\n\n")
                    return 'no'

            except asyncio.TimeoutError:
                tty.write(f"\n  ⏰ Timeout ({timeout}s). Denying action.\n\n")
                tty.flush()
                logger.warning(f"Approval timed out for '{tool_name}'")
                return 'no'

    except OSError:
        # /dev/tty not available (CI, Docker, SSH without TTY)
        logger.warning(
            f"Cannot acquire terminal (/dev/tty). "
            f"Denying '{tool_name}' securely. "
            f"(ASK rules become DENY in headless environments)"
        )
        return 'no'


def _indent(text: str, spaces: int) -> str:
    """Indent each line of text."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.split("\n"))
