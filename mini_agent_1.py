#!/usr/bin/env python3

"""A minimal command-line chat program powered by Kimi K3."""

import json
import os
import urllib.request
import glob as globlib
import re
import subprocess

API_KEY = os.environ.get("MOONSHOT_API_KEY")
API_URL = "https://api.kimi.com/coding/v1/messages"
MODEL = "k3"

SYSTEM_PROMPT = (
    f"Concise coding assistant. "
    f"Operating system: Windows. "
    f"Current working directory: {os.getcwd()}. "
    f"The bash tool runs commands through Windows cmd.exe. "
    f"Use relative paths unless the user specifies otherwise."
)


def read(args):
    lines = open(args["path"], encoding="utf-8").readlines()
    offset = args.get("offset", 0)
    limit = args.get("limit", len(lines))
    selected = lines[offset : offset + limit]

    return "".join(
        f"{offset + index + 1:4}| {line}" for index, line in enumerate(selected)
    )  # "" 表示拼接时不插入任何分隔符


def write(args):
    with open(args["path"], "w", encoding="utf-8") as file:
        file.write(args["content"])

    return "ok"


def edit(args):
    with open(args["path"], encoding="utf-8") as file:
        text = file.read()

    old = args["old"]
    new = args["new"]

    if old not in text:
        return "error: old string not found"

    count = text.count(old)

    if not args.get("all") and count > 1:
        return (
            f"error: old string appears {count} times, " "must be unique (use all=true)"
        )
    # get 如果字典里有这个键，就返回对应的值；如果字典里没有这个键，它不会报错，而是返回 None
    if args.get("all"):
        replacement = text.replace(old, new)
    else:
        replacement = text.replace(old, new, 1)

    with open(args["path"], "w", encoding="utf-8") as file:
        file.write(replacement)

    return "ok"


def glob(args):
    pattern = (args.get("path", ".") + "/" + args["pat"]).replace("//", "/")

    files = globlib.glob(pattern, recursive=True)

    files = sorted(
        files,
        key=lambda path: (os.path.getmtime(path) if os.path.isfile(path) else 0),
        reverse=True,
    )

    return "\n".join(files) or "none"


def grep(args):
    pattern = re.compile(args["pat"])
    hits = []

    for filepath in globlib.glob(
        args.get("path", ".") + "/**",
        recursive=True,
    ):
        try:
            with open(filepath, encoding="utf-8") as file:
                for line_number, line in enumerate(file, 1):
                    if pattern.search(line):
                        hits.append(f"{filepath}:{line_number}:{line.rstrip()}")
        except Exception:
            pass

    return "\n".join(hits[:50]) or "none"


def bash(args):
    process = subprocess.Popen(
        args["cmd"],
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    output_lines = []

    try:
        while True:
            line = process.stdout.readline()

            if not line and process.poll() is not None:
                break

            if line:
                print(f" | {line.rstrip()}", flush=True)
                output_lines.append(line)

        process.wait(timeout=30)

    except subprocess.TimeoutExpired:
        process.kill()
        output_lines.append("\n(timed out after 30s)")

    return "".join(output_lines).strip() or "(empty)"


TOOLS = {
    "read": (
        "Read file with line numbers. offset is the zero-based start line; limit is the maximum number of lines to return",
        {
            "path": "string",
            "offset": "number?",
            "limit": "number?",
        },
        read,
    ),
    "write": (
        "Write content to file",
        {
            "path": "string",
            "content": "string",
        },
        write,
    ),
    "edit": (
        "Replace old text with new text in a file. old must be unique unless all is true",
        {
            "path": "string",
            "old": "string",
            "new": "string",
            "all": "boolean?",
        },
        edit,
    ),
    "glob": (
        "Find files by pattern, sorted by modification time",
        {
            "pat": "string",
            "path": "string?",
        },
        glob,
    ),
    "grep": (
        "Search files for a regular expression",
        {
            "pat": "string",
            "path": "string?",
        },
        grep,
    ),
    "bash": (
        "Run a shell command",
        {
            "cmd": "string",
        },
        bash,
    ),
}


def run_tool(name, args):
    try:
        function = TOOLS[name][2]
        return function(args)
    except Exception as error:
        return f"error: {error}"


def make_schema():
    result = []

    for name, (description, params, _function) in TOOLS.items():
        properties = {}
        required = []

        for param_name, param_type in params.items():
            is_optional = param_type.endswith("?")
            base_type = param_type.rstrip("?")

            properties[param_name] = {
                "type": "integer" if base_type == "number" else base_type
            }

            if not is_optional:
                required.append(param_name)

        result.append(
            {
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )

    return result


def call_api(messages):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(
            {
                "model": MODEL,
                "max_tokens": 8192,
                "system": SYSTEM_PROMPT,
                "messages": messages,
                "tools": make_schema(),
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def main():
    if not API_KEY:
        print("MOONSHOT_API_KEY is not set")
        return

    print(f"mini agent | {MODEL}\n")
    messages = []

    # Conversation loop: wait for user input.
    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue
            if user_input in ("/q", "exit"):
                break
            if user_input == "/c":
                messages = []
                print("conversation cleared")
                continue

            messages.append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            # Agent loop: keep calling the API until no tools are requested.
            while True:
                response = call_api(messages)
                content = response.get(
                    "content", []
                )  # if "content" in response:content = response["content"]else:content = []
                tool_results = []

                for block in content:
                    if block["type"] == "text":
                        print(f"\n{block['text']}\n")

                    if block["type"] == "tool_use":
                        tool_name = block["name"]
                        tool_args = block["input"]

                        print(f"\n[tool] {tool_name}({tool_args})")

                        result = run_tool(tool_name, tool_args)
                        print(result)

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": result,
                            }
                        )

                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )

                if not tool_results:
                    break

                messages.append(
                    {
                        "role": "user",
                        "content": tool_results,
                    }
                )

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as error:
            print(f"error: {error}")


if __name__ == "__main__":
    main()
