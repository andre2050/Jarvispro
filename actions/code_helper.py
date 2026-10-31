import subprocess
import sys
import json
import re
import time
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR           = get_base_dir()
API_CONFIG_PATH    = BASE_DIR / "config" / "api_keys.json"
DESKTOP            = Path.home() / "Desktop"
MAX_BUILD_ATTEMPTS = 3
# Model choice lives in core/gemini.py, and so does the timeout and the
# fallback ladder. Writing a model name here is what left this file hanging
# forever whenever that one alias was unwell.
from core import gemini
from core.protecao import engolida as _engolida


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return __import__("core.cofre", fromlist=["resolver"]).resolver(json.load(f))["gemini_api_key"]


def _get_gemini(tier: str = gemini.SMART):
    """Writing and fixing code is the reasoning tier; a 60s deadline because a
    whole file can come back."""
    class _W:
        def generate_content(self, contents):
            resp = gemini.call(contents, tier=tier, timeout_ms=60000)
            if resp is None:
                raise RuntimeError("every Gemini model on the ladder failed")
            return resp

    return _W()


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[^\n]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


# Linguagem -> extensão. Qualquer linguagem fora desta lista é resolvida pelo
# Gemini (_ext_por_ia), então o NEXUS escreve scripts em qualquer linguagem.
_EXT_MAP = {
    "python": ".py", "py": ".py", "python3": ".py",
    "javascript": ".js", "js": ".js", "node": ".js", "nodejs": ".js",
    "typescript": ".ts", "ts": ".ts",
    "html": ".html", "css": ".css", "scss": ".scss", "xml": ".xml",
    "java": ".java", "kotlin": ".kt", "scala": ".scala", "groovy": ".groovy",
    "c": ".c", "cpp": ".cpp", "c++": ".cpp", "csharp": ".cs", "c#": ".cs",
    "objective-c": ".m", "swift": ".swift", "dart": ".dart",
    "bash": ".sh", "shell": ".sh", "sh": ".sh", "zsh": ".sh",
    "powershell": ".ps1", "ps1": ".ps1",
    "batch": ".bat", "bat": ".bat", "cmd": ".bat",
    "sql": ".sql", "json": ".json", "yaml": ".yml", "yml": ".yml",
    "toml": ".toml", "markdown": ".md", "md": ".md",
    "rust": ".rs", "go": ".go", "golang": ".go", "zig": ".zig",
    "ruby": ".rb", "php": ".php", "perl": ".pl", "lua": ".lua",
    "r": ".R", "julia": ".jl", "matlab": ".m", "octave": ".m",
    "haskell": ".hs", "elixir": ".exs", "erlang": ".erl", "clojure": ".clj",
    "fsharp": ".fs", "f#": ".fs", "ocaml": ".ml", "lisp": ".lisp", "scheme": ".scm",
    "vba": ".bas", "vbscript": ".vbs", "autohotkey": ".ahk", "ahk": ".ahk",
    "assembly": ".asm", "asm": ".asm", "fortran": ".f90", "cobol": ".cob",
    "pascal": ".pas", "delphi": ".pas", "nim": ".nim", "crystal": ".cr",
    "solidity": ".sol", "gdscript": ".gd", "glsl": ".glsl",
    "dockerfile": ".dockerfile", "makefile": ".mk", "cmake": ".cmake",
    "txt": ".txt", "text": ".txt",
}


def _ext_por_ia(lang: str) -> str:
    """Pergunta ao Gemini a extensão de arquivo de uma linguagem fora do mapa."""
    try:
        ans = _get_gemini(gemini.FAST).generate_content(
            f"What is the conventional source-file extension for the programming or scripting "
            f"language '{lang}'? Reply with ONLY the extension including the dot (example: .py)."
        ).text.strip().lower().strip("`'\". \n")
        if re.fullmatch(r"\.[a-z0-9+#_-]{1,10}", ans):
            return ans
    except Exception as e:
        print(f"[Code] Extension lookup failed ({e})")
    return ".txt"


def _ext_for(language: str) -> str:
    lang = (language or "python").strip().lower()
    ext = _EXT_MAP.get(lang)
    if ext:
        return ext
    ext = _ext_por_ia(lang)
    _EXT_MAP[lang] = ext          # lembra para os próximos pedidos
    return ext


def _resolve_save_path(output_path: str, language: str) -> Path:
    if output_path:
        p = Path(output_path)
        return p if p.is_absolute() else DESKTOP / p
    return DESKTOP / f"jarvis_code{_ext_for(language)}"


def _read_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        return "", "No file path provided."
    p = Path(file_path)
    if not p.exists():
        return "", f"File not found: {file_path}"
    try:
        return p.read_text(encoding="utf-8"), ""
    except Exception as e:
        return "", f"Could not read file: {e}"


def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved to: {path}"
    except Exception as e:
        return f"Could not save: {e}"


def _preview(code: str, lines: int = 10) -> str:
    all_lines = code.splitlines()
    preview   = "\n".join(all_lines[:lines])
    suffix    = f"\n... ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    return preview + suffix


def _has_error(output: str) -> bool:
    error_signals = ["error", "exception", "traceback", "syntaxerror",
                     "nameerror", "typeerror", "stderr", "failed", "crash"]
    return any(s in output.lower() for s in error_signals)


def _take_screenshot() -> Path | None:
    try:
        import pyautogui
        screenshot_path = Path.home() / "Desktop" / f"jarvis_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
        print(f"[Code] 📸 Screenshot: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"[Code] ⚠️ Screenshot failed: {e}")
        return None


def _image_to_base64(path: Path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode("utf-8")


_VALID_INTENTS = {"write", "edit", "explain", "run", "build", "screen_debug", "optimize"}


def _detect_intent(description: str, file_path: str, code: str) -> str:
    """
    Language-independent intent detection — NO fixed keyword list.
    Whatever language the user speaks, the description is classified by
    Gemini. If the API is unreachable, it falls back to language-agnostic
    structural hints (does the file exist on disk, was code provided).
    """
    desc        = (description or "").strip()
    file_exists = bool(file_path) and Path(file_path).exists()

    if desc:
        try:
            ctx = []
            if file_path:
                ctx.append(f"a file path is provided (exists on disk: {file_exists})")
            if code:
                ctx.append("an inline code snippet is provided")
            prompt = (
                "Classify a coding assistant request into exactly ONE intent word.\n"
                "The request may be written in ANY language.\n\n"
                f"Request: {desc}\n"
                + (f"Context: {'; '.join(ctx)}\n" if ctx else "")
                + "\nIntents:\n"
                "  write        = create new code from scratch\n"
                "  edit         = modify an existing file\n"
                "  explain      = describe what given code/file does\n"
                "  run          = execute an existing file\n"
                "  build        = write code, run it, and iterate until it works\n"
                "  screen_debug = analyze an error currently visible on the user's screen\n"
                "  optimize     = refactor / clean up / speed up existing code\n\n"
                "Reply with ONLY the intent word, nothing else."
            )
            ans = _get_gemini().generate_content(prompt).text.strip().lower()
            ans = ans.strip("`'\". \n")
            if ans in _VALID_INTENTS:
                return ans
        except Exception as e:
            print(f"[Code] Intent classification failed ({e}) — structural fallback")

    # Structural fallback — not tied to any language
    if file_exists:
        return "edit" if desc else "explain"
    if code:
        return "explain"
    return "write"

def _write(description: str, language: str, output_path: str, player=None) -> tuple[str, Path]:
    lang  = language or "python"
    model = _get_gemini()

    prompt = f"""You are an expert {lang} developer.
Write a complete, ready-to-run {lang} script/program for the description below.
{lang} may be ANY language (general-purpose, shell, scripting, query or markup language) —
follow that language's own idioms and file conventions.

Rules:
- Output ONLY the code. No explanation, no markdown, no backticks.
- The file must be complete and runnable as-is (imports, entry point, shebang if the language uses one).
- Add helpful inline comments in the language's own comment syntax.
- Handle errors and edge cases properly.
- Use modern best practices.

Description: {description}

Code:"""

    response = model.generate_content(prompt)
    code     = _clean_code(response.text)
    path     = _resolve_save_path(output_path, lang)
    _save_file(path, code)
    return code, path


def _fix_code(code: str, error_output: str, description: str) -> str:
    model  = _get_gemini()
    prompt = f"""You are an expert debugger.
The code below failed with the following error. Fix it.
Return ONLY the corrected code — no explanation, no markdown, no backticks.

Original goal: {description}

Error:
{error_output[:2000]}

Broken code:
{code}

Fixed code:"""

    response = model.generate_content(prompt)
    return _clean_code(response.text)


def _run_file(path: Path, args: list, timeout: int) -> str:
    interpreters = {
        ".py":  [sys.executable],
        ".js":  ["node"],
        ".ts":  ["ts-node"],
        ".sh":  ["bash"],
        ".ps1": ["powershell", "-File"],
        ".rb":  ["ruby"],
        ".php": ["php"],
        ".pl":  ["perl"],
        ".lua": ["lua"],
        ".R":   ["Rscript"],
        ".jl":  ["julia"],
        ".go":  ["go", "run"],
        ".bat": ["cmd", "/c"],
        ".vbs": ["cscript", "//nologo"],
        ".ahk": ["AutoHotkey"],
        ".dart": ["dart", "run"],
        ".swift": ["swift"],
        ".kt":  ["kotlin"],
        ".exs": ["elixir"],
        ".hs":  ["runghc"],
        ".java": ["java"],          # Java 11+ roda o arquivo direto
        ".sql": None,
    }
    interp = interpreters.get(path.suffix.lower()) or interpreters.get(path.suffix)
    if not interp:
        return (f"O arquivo {path.name} foi escrito, mas o NEXUS não sabe executar {path.suffix or 'esse tipo'} "
                f"automaticamente. O código está salvo e pronto para você usar.")

    try:
        # 1.4.3 — stdin vazio: um input() no programa terminava em "Timed out
        # after 30s" (esperava o teclado de um console que não existe).
        result = subprocess.run(
            interp + [str(path)] + (args or []),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(path.parent),
            stdin=subprocess.DEVNULL,
        )
        output = result.stdout.strip()
        error  = result.stderr.strip()
        parts  = []
        if output: parts.append(f"Output:\n{output}")
        if error:  parts.append(f"Stderr:\n{error}")
        return "\n\n".join(parts) if parts else "Executed with no output."

    except subprocess.TimeoutExpired as e:
        parcial = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        return (f"Timed out after {timeout}s — the program kept running (a window, a server "
                f"or a loop)." + (f"\nOutput so far:\n{parcial.strip()[-1500:]}" if parcial and parcial.strip() else ""))
    except FileNotFoundError:
        return f"Interpreter not found: {interp[0]}."
    except Exception as e:
        return f"Execution error: {e}"


def _build(description, language, output_path, args, timeout, speak=None, player=None) -> str:
    if not description:
        return "Please describe what you want me to build, sir."

    if player:
        player.write_log("[Code] Build started...")

    lang = language or "python"

    try:
        code, path = _write(description, lang, output_path, player)
        print(f"[Code] ✅ Written: {path}")
    except Exception as e:
        msg = f"Could not write initial code: {e}"
        if speak: speak(msg)
        return msg

    last_output = ""
    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[Code] 🔄 Attempt {attempt}/{MAX_BUILD_ATTEMPTS}")
        if player:
            player.write_log(f"[Code] Attempt {attempt}...")

        last_output = _run_file(path, args, timeout)

        if not _has_error(last_output):
            msg = (
                f"Build complete, sir. "
                f"The code is working after {attempt} attempt{'s' if attempt > 1 else ''}. "
                f"Saved to {path}."
            )
            if speak: speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"

        print(f"[Code] ⚠️ Error on attempt {attempt}, fixing...")
        if player:
            player.write_log(f"[Code] Fixing (attempt {attempt})...")

        try:
            code = _fix_code(code, last_output, description)
            _save_file(path, code)
        except Exception as e:
            msg = f"Could not fix code on attempt {attempt}: {e}"
            if speak: speak(msg)
            return msg

    msg = (
        f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts, sir. "
        f"The last error was: {last_output[:200]}"
    )
    if speak: speak(msg)
    return f"{msg}\n\nLast code saved to: {path}"

def _write_action(description, language, output_path, player) -> str:
    if not description:
        return "Please describe what you want me to write, sir."
    if player:
        player.write_log("[Code] Writing code...")
    try:
        code, path = _write(description, language, output_path, player)
        print(f"[Code] ✅ Written: {path}")
        return f"Code written. Saved to: {path}\n\nPreview:\n{_preview(code)}"
    except Exception as e:
        return f"Could not generate code: {e}"


def _edit_action(file_path, instruction, player) -> str:
    if not file_path:
        return "Please provide a file path to edit, sir."
    if not instruction:
        return "Please describe what change to make, sir."

    content, err = _read_file(file_path)
    if err:
        return err

    if player:
        player.write_log("[Code] Editing file...")

    model  = _get_gemini()
    prompt = f"""You are an expert code editor.
Apply the following change to the code below.
Return ONLY the complete updated code — no explanation, no markdown, no backticks.

Change: {instruction}

Original code:
{content}

Updated code:"""

    try:
        response = model.generate_content(prompt)
        edited   = _clean_code(response.text)
    except Exception as e:
        return f"Could not edit code: {e}"

    status = _save_file(Path(file_path), edited)
    print(f"[Code] ✅ Edited: {file_path}")
    return f"File edited. {status}\n\nPreview:\n{_preview(edited)}"


def _explain_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to explain, sir."

    if player:
        player.write_log("[Code] Analyzing code...")

    model  = _get_gemini()
    prompt = f"""Explain what this code does in simple, clear language.
Focus on: what it does, how it works, and any important details.
Be concise — 3 to 6 sentences maximum.

Code:
{code[:4000]}

Explanation:"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Could not explain code: {e}"


def _run_action(file_path, args, timeout, player) -> str:
    if not file_path:
        return "Please provide a file path to run, sir."
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Running {p.name}...")
    return _run_file(p, args, timeout)


def _optimize_action(file_path, code, language, output_path, player) -> str:

    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to optimize, sir."

    if player:
        player.write_log("[Code] Optimizing code...")

    lang  = language or "python"
    model = _get_gemini()

    prompt = f"""You are an expert {lang} developer and code reviewer.
Optimize the following code for:
1. Performance — eliminate unnecessary operations, use efficient data structures
2. Readability — clear variable names, proper formatting, logical structure
3. Best practices — modern {lang} patterns, error handling, type hints if applicable
4. Remove dead code, redundant comments, and unnecessary complexity

Return ONLY the optimized code — no explanation, no markdown, no backticks.

Original code:
{code[:6000]}

Optimized code:"""

    try:
        response  = model.generate_content(prompt)
        optimized = _clean_code(response.text)
    except Exception as e:
        return f"Could not optimize code: {e}"

    # Kaydet
    if file_path:
        save_path = Path(file_path)
    else:
        save_path = _resolve_save_path(output_path, lang)

    status = _save_file(save_path, optimized)
    print(f"[Code] ✅ Optimized: {save_path}")

    original_lines  = len(code.splitlines())
    optimized_lines = len(optimized.splitlines())
    diff = original_lines - optimized_lines

    return (
        f"Code optimized. {status}\n"
        f"Lines: {original_lines} → {optimized_lines} "
        f"({'−' if diff > 0 else '+'}{abs(diff)} lines)\n\n"
        f"Preview:\n{_preview(optimized)}"
    )


def _screen_debug_action(description, file_path, player, speak=None) -> str:

    if player:
        player.write_log("[Code] Taking screenshot for analysis...")

    print("[Code] 📸 Capturing screen for debug...")


    screenshot_path = _take_screenshot()
    if not screenshot_path:
        return "Could not take screenshot, sir. Please make sure PyAutoGUI is installed."


    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[Code] ⚠️ Could not read file: {err}")

    try:
        from google.genai import types

        image_bytes  = screenshot_path.read_bytes()
        image_base64 = _image_to_base64(screenshot_path)

        user_question = description or "What error or problem do you see on the screen? How can it be fixed?"

        context = ""
        if file_content:
            context = f"\n\nAdditionally, here is the related file content:\n```\n{file_content[:4000]}\n```"

        analysis_prompt = f"""You are an expert programmer and debugger analyzing a screenshot.

User's question: {user_question}{context}

Please:
1. Identify any errors, exceptions, or problems visible on the screen
2. Explain what is causing the problem in simple terms
3. Provide a concrete fix or solution
4. If there's code visible, show the corrected version

Be specific and actionable. If you see an error message, quote it exactly."""

        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            analysis_prompt,
        ]

        response = gemini.call(contents, tier=gemini.SMART, timeout_ms=45_000)
        if response is None:
            return "Sir, I couldn't reach Gemini to analyse that screenshot."

        analysis = (response.text or "").strip()
        print("[Code] ✅ Screen analysis complete")

        try:
            screenshot_path.unlink()
        except Exception:
            _engolida("actions/code_helper.py:569")

        if file_path and file_content:

            code_match = re.search(r"```[a-zA-Z]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                save_path  = Path(file_path)
                _save_file(save_path, fixed_code)
                analysis += f"\n\n✅ Fixed code has been saved to: {file_path}"
                print(f"[Code] ✅ Fixed code saved: {file_path}")

        return analysis

    except Exception as e:

        try:
            screenshot_path.unlink()
        except Exception:
            _engolida("actions/code_helper.py:588")
        return f"Screen analysis failed: {e}"


_CHECADORES = {".js": ["node", "--check"], ".mjs": ["node", "--check"], ".ts": ["tsc", "--noEmit"],
               ".c": ["gcc", "-fsyntax-only"], ".cpp": ["g++", "-fsyntax-only"]}


def _check_action(file_path: str) -> str:
    """Confere a sintaxe SEM executar o código (Python direto; outras linguagens só se
    o compilador existir)."""
    import ast
    import shutil
    arq = Path(file_path).expanduser()
    if not arq.is_file():
        return "Não encontrei o arquivo de código."
    if arq.stat().st_size > 2_000_000:
        return "Arquivo grande demais para verificação rápida (limite de 2 MB)."
    ext = arq.suffix.lower()
    if ext == ".py":
        try:
            ast.parse(arq.read_text(encoding="utf-8-sig"), filename=str(arq))
            return f"Sintaxe Python válida: {arq.name}. O código não foi executado."
        except SyntaxError as e:
            return f"Erro de sintaxe em {arq.name}, linha {e.lineno}: {e.msg}"
    cmd = _CHECADORES.get(ext)
    if not cmd:
        return f"Verificação automática de sintaxe não configurada para {ext or 'arquivo sem extensão'}."
    if not shutil.which(cmd[0]):
        return f"Arquivo {arq.name} reconhecido, mas {cmd[0]} não está instalado. Nenhum código foi executado."
    try:
        proc = subprocess.run(cmd + [str(arq)], capture_output=True, text=True, timeout=15,
                              cwd=str(arq.parent), shell=False)
    except subprocess.TimeoutExpired:
        return "A verificação excedeu o limite de 15 segundos."
    saida = (proc.stderr or proc.stdout).strip()
    return ("Verificação passou: " if proc.returncode == 0 else "A verificação encontrou problemas: ") \
        + (saida[:1200] if saida else arq.name)


def code_helper(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    """
    Called from main.py.

    parameters:
        action      : write | edit | explain | run | build | screen_debug | optimize | auto
        description : What the code should do / what change to make / what problem to analyze
        language    : Programming language (default: python)
        output_path : Where to save — user specifies full path or filename
        file_path   : Path to existing file (edit / explain / run / build / optimize)
        code        : Raw code string (explain/optimize without a file)
        args        : CLI argument list for run/build
        timeout     : Execution timeout in seconds (default: 30)
    """
    p           = parameters or {}
    action      = p.get("action", "auto").lower().strip()
    description = p.get("description", "").strip()
    language    = p.get("language", "python").strip()
    output_path = p.get("output_path", "").strip()
    file_path   = p.get("file_path", "").strip()
    code        = p.get("code", "").strip()
    args        = p.get("args", [])
    timeout     = int(p.get("timeout", 30))

    if action == "auto":
        action = _detect_intent(description, file_path, code)
        print(f"[Code] 🤖 Auto-detected: {action}")

    if action == "write":
        return _write_action(description, language, output_path, player)

    elif action == "edit":
        return _edit_action(
            file_path,
            description or p.get("instruction", ""),
            player
        )

    elif action == "explain":
        return _explain_action(file_path, code, player)

    elif action == "run":
        return _run_action(file_path, args, timeout, player)

    elif action == "build":
        return _build(description, language, output_path, args, timeout, speak, player)

    elif action == "optimize":
        return _optimize_action(file_path, code, language, output_path, player)

    elif action == "screen_debug":
        return _screen_debug_action(description, file_path, player, speak)

    elif action in ("check", "syntax"):
        return _check_action(file_path)

    else:
        return f"Unknown action: '{action}'. Use write, edit, explain, run, build, optimize, check or screen_debug."


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "code_helper",
    "description": "Writes (action=write) a script or program in ANY programming language when the user asks to create one, and also edits, explains, runs, builds or syntax-checks code files (action=check validates syntax without running anything). Always pass the language the user asked for; the file is saved on the Desktop unless output_path says otherwise.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "write | edit | explain | run | build | check | auto (default: auto)"
            },
            "description": {
                "type": "STRING",
                "description": "What the code should do or what change to make"
            },
            "language": {
                "type": "STRING",
                "description": "ANY programming or scripting language the user names (python, javascript, c#, rust, go, lua, bash, powershell, sql, ...). Default: python"
            },
            "output_path": {
                "type": "STRING",
                "description": "Where to save the file"
            },
            "file_path": {
                "type": "STRING",
                "description": "Path to existing file for edit/explain/run/build"
            },
            "code": {
                "type": "STRING",
                "description": "Raw code string for explain"
            },
            "args": {
                "type": "STRING",
                "description": "CLI arguments for run/build"
            },
            "timeout": {
                "type": "INTEGER",
                "description": "Execution timeout in seconds (default: 30)"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": code_helper,
}
