"""
Shared helpers for the tests of the memory system.

Run the suite from the root of the repository:

    poetry run python -m unittest discover -s test -v

What they do NOT use: the network (the LLM is a scripted fake), the real log files (the base logger is replaced by
a quiet one) nor the real database (every test works in a temporary directory).

The tests also run where `pyxavi` / `google-genai` are not installed (a CI box, a sandbox): then minimal stand-ins are
used for them. With the real libraries installed, the real ones are used.
"""
import json
import logging
import os
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import yaml  # noqa: E402  (a dependency of pyxavi)



# ------------------------------------------------------------------ stand-ins, only when the real thing is missing

def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def read_yaml(path: str) -> dict:
    return yaml.safe_load(read_file(path))


def _install_pyxavi_stand_in():
    class Dictionary(dict):
        def key_exists(self, key): return key in self
        def get(self, key, default=None): return dict.get(self, key, default)
        def set(self, key, value): self[key] = value

    class Config:
        def __init__(self, filename=None):
            with open(filename) as handle:
                self.d = yaml.safe_load(handle) if filename else {}

        def get(self, key, default=None):
            cur = self.d
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return default
            return cur

        def set(self, key, value):
            cur, parts = self.d, key.split(".")
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = value

        def key_exists(self, key): return self.get(key, KeyError) is not KeyError

    class Logger:
        def __init__(self, config=None, base_path=""): pass
        def get_logger(self): return logging.getLogger("pitxu_test")

    module = types.ModuleType("pyxavi")
    module.Config, module.Dictionary, module.Logger = Config, Dictionary, Logger
    module.Text = type("Text", (), {})  # pitxu's Text extends it, and only uses its own methods here.
    module.full_stack = lambda: ""
    module.dd = lambda *args: None
    module.TerminalColor = type("TerminalColor", (), {"RED_BRIGHT": "", "END": ""})
    sys.modules["pyxavi"] = module


def _install_genai_stand_in():
    class _Error(Exception):
        pass

    class _Anything:
        def __init__(self, *args, **kwargs): pass

    errors = types.ModuleType("google.genai.errors")
    errors.ClientError = errors.ServerError = _Error
    genai_types = types.ModuleType("google.genai.types")
    genai_types.Schema = genai_types.HttpOptions = genai_types.GenerateContentConfig = _Anything
    genai_types.Type = type("Type", (), {k: k for k in ("OBJECT", "ARRAY", "STRING", "INTEGER", "BOOLEAN")})
    genai = types.ModuleType("google.genai")
    genai.types, genai.errors, genai.Client = genai_types, errors, _Anything
    google = types.ModuleType("google")
    google.genai = genai
    sys.modules.update({"google": google, "google.genai": genai, "google.genai.errors": errors,
                        "google.genai.types": genai_types})


def _namespace(name, relative_dir):
    """ A package without running its __init__ (some of them import the whole application). """
    module = types.ModuleType(name)
    module.__path__ = [os.path.join(REPO, relative_dir)]
    sys.modules[name] = module


try:
    import pyxavi  # noqa: F401
    REAL_PYXAVI = True
except ImportError:
    _install_pyxavi_stand_in()
    REAL_PYXAVI = False

try:
    import google.genai  # noqa: F401
except ImportError:
    _install_genai_stand_in()

if not REAL_PYXAVI:
    # Their __init__ files import hardware and the whole app; the stand-in mode only needs the modules inside.
    for package, folder in [("pitxu.lib.abstract", "pitxu/lib/abstract"), ("pitxu.lib.command", "pitxu/lib/command"),
                            ("pitxu.lib.command.stateful", "pitxu/lib/command/stateful")]:
        _namespace(package, folder)
    for name, attrs in {
        "pitxu.lib.abstract.command": {"Command": type("Command", (), {"default_empty_callback": lambda *a, **k: None, "close": lambda s: None})},
        "pitxu.lib.interaction.interaction": {"Interaction": object},
        "pitxu.lib.interaction.shortcuts.status": {"Status": object},
    }.items():
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
    for package, folder in [("pitxu.lib.interaction", "pitxu/lib/interaction"),
                            ("pitxu.lib.interaction.shortcuts", "pitxu/lib/interaction/shortcuts")]:
        _namespace(package, folder)

# A quiet base logger: the tests must not open the log files of the application.
import pitxu.lib.abstract.pyxavi as _abstract_pyxavi  # noqa: E402
logging.getLogger("pitxu_test").setLevel(logging.CRITICAL)
_abstract_pyxavi.get_base_logger = lambda config=None, base_path="": logging.getLogger("pitxu_test")

from pyxavi import Config, Dictionary  # noqa: E402
from pitxu.lib.database.db_sqlite import DbSqlite  # noqa: E402
from pitxu.lib.utils.memory import Memory  # noqa: E402
from pitxu.lib.utils.memory_consolidator import MemoryConsolidator  # noqa: E402
from pitxu.lib.support_process.summarizer import Summarizer  # noqa: E402
from pitxu.lib.command.stateful.memory import StatefulMemory  # noqa: E402


# ------------------------------------------------------------------ configuration and environment

def cfg(tmp: str, **overrides) -> Config:
    """
    The real default configs (the `.dist` files, so the tests do not depend on the personal ones), a fixed preload,
    and the storage in a temporary directory. `overrides` are dotted keys:
    `cfg(tmp, **{"memory.consolidation.batch_size": 3})`.
    """
    merged = {}
    for path in ["config/main.yaml.dist", "config/memory.yaml.dist", "config/database.yaml.dist", "config/language.yaml.dist", "config/chatbot.yaml.dist"]:
        merged.update(read_yaml(os.path.join(REPO, path)))
    merged.update(read_yaml(os.path.join(FIXTURES, "memory_preload.yaml")))
    merged["app"] = {"supported_languages": ["en", "ca", "de", "es"], "default_language": "ca"}
    merged["storage"] = {"path": tmp + "/"}
    file_path = os.path.join(tmp, "test_config.yaml")
    with open(file_path, "w") as handle:
        yaml.safe_dump(merged, handle, allow_unicode=True)
    config = Config(filename=file_path)
    for key, value in overrides.items():
        config.set(key, value)
    return config


def methods_of(relative_path: str, names: list[str], namespace: dict = None):
    """
    A class with only the given methods of a file of the application, taken from its source without importing it
    (some modules need the whole stack). `namespace` holds the globals that the methods use.
    """
    import ast
    tree = ast.parse(read_file(os.path.join(REPO, relative_path)))
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
    missing = set(names) - {function.name for function in functions}
    if missing:
        raise AssertionError(f"{relative_path} has no method {sorted(missing)}")
    module = ast.Module(body=[ast.ClassDef(name="Holder", bases=[], keywords=[], body=functions, decorator_list=[], type_params=[])],
                        type_ignores=[])
    ast.fix_missing_locations(module)
    scope = dict(namespace or {})
    exec(compile(module, relative_path, "exec"), scope)
    return scope["Holder"]


def params(**extra) -> Dictionary:
    return Dictionary({"api_key": "test-key", "base_path": REPO, **extra})


def check(label, condition):
    """ One assertion that tells what was being checked. """
    if not condition:
        raise AssertionError(label)


def rows(memory: Memory, sql: str, *args) -> list[dict]:
    return [dict(row) for row in memory.db.connection.execute(sql, args).fetchall()]


q = rows


def add(memory: Memory, summary: str, content: str = "x", language: str = "en") -> int:
    return memory.create_short_memory_entry(summary, content, language=language)["id"]


def raises_database_error(function):
    try:
        function()
        return None
    except sqlite3.DatabaseError as error:
        return str(error)


class Log:
    """ A logger that keeps what it was told. """
    def __init__(self): self.lines = []
    def info(self, message): self.lines.append(message)
    warning = error = debug = info


# ------------------------------------------------------------------ the scripted LLM

FAKE = {"calls": [], "fail_consolidation": False, "drop_translation": set(), "bad_ops": None, "summarize": None}


def reset_fake():
    FAKE.update({"calls": [], "fail_consolidation": False, "drop_translation": set(), "bad_ops": None, "summarize": None})


def fake_llm(self, prompt, schema, model=None, settings="summarization", purpose="summarization"):
    """ Stands in for Memory.request_llm_json: answers by the `purpose` from what the prompt carries. """
    FAKE["calls"].append(purpose)
    if purpose == "summarization":
        reply = FAKE["summarize"]
        return None if reply is None else json.dumps(reply)
    data = json.loads(prompt.rsplit("# Input\n", 1)[1])
    if purpose == "memory translation":
        out = [{"language": lang, "summary": f"[{lang}] {data['summary']}", "content": f"[{lang}] {data['content']}"}
               for lang in data["target_languages"] if lang not in FAKE["drop_translation"]]
        return json.dumps({"translations": out})
    # consolidation
    if FAKE["fail_consolidation"]:
        return None
    if FAKE["bad_ops"] is not None:
        return json.dumps({"operations": FAKE["bad_ops"](data)})

    def find(word):
        return next((t for t in data["existing_topics"] if word in t["summary"].lower()), None)

    operations, sold = [], []
    for entry in data["pending_entries"]:
        key = entry["summary"].lower()
        if "sold" in key:
            sold.append(entry["id"])
        elif "home" in key:
            topic = find("locations")
            operations.append({"action": "update", "topic_id": topic["topic_id"], "source_ids": [entry["id"]],
                               "language": data["language"], "summary": topic["summary"],
                               "content": topic["content"] + "\n- UPDATED home"})
        elif "ducati" in key:
            topic = find("veh")
            operations.append({"action": "update", "topic_id": topic["topic_id"], "source_ids": [entry["id"]],
                               "language": data["language"], "summary": topic["summary"],
                               "content": topic["content"] + "\n- DUCATI"})
        elif "climbing" in key:
            operations.append({"action": "create", "source_ids": [entry["id"]], "language": data["language"],
                               "summary": "Hobbies", "content": "Climbing"})
        elif "hello" in key:
            operations.append({"action": "ignore", "source_ids": [entry["id"]]})
    if sold:
        topic = find("vehicles")
        operations.append({"action": "update", "topic_id": topic["topic_id"], "source_ids": sold,
                           "language": data["language"], "summary": topic["summary"],
                           "content": topic["content"] + "\n- SOLD Montesa"})
    return json.dumps({"operations": operations})


def env(abort=None, **overrides):
    """
    A migrated database in a temporary directory with the preload done, and a consolidator that uses it.
    Returns (tmp, config, writer, consolidator).
    """
    tmp = tempfile.mkdtemp()
    config = cfg(tmp, **{"memory.consolidation.batch_size": 3, **overrides})
    database = DbSqlite(config=config, params=params())
    database.migrate_db()
    database.close()
    writer = Memory(config=config, params=params(long_term_writer=True, language="en"))
    writer.backfill_legacy_language()
    writer.preload_memory()
    consolidator = MemoryConsolidator(config=config, params=params(), memory=writer, should_abort=abort)
    reset_fake()
    return tmp, config, writer, consolidator


def tools(config, language="en") -> StatefulMemory:
    class _StatusShortcuts:
        def add_new_status_line(self, text): pass
    return StatefulMemory(config=config, params=params(language=language, status_shortcuts=_StatusShortcuts()))
