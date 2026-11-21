# Tests

```
poetry run python -m unittest discover -s test -v      # or: make unittests
```

The tests of the application (memory, database, consolidation, shutdown, config). They do not use the network (the
LLM is a scripted fake), the real logs, nor the real database: each test works in a temporary directory, with the
default configuration (`config/*.yaml.dist`) and a fixed preload (`test/fixtures/memory_preload.yaml`).

If `pyxavi` or `google-genai` are not installed, `support.py` uses minimal stand-ins, so they run anywhere.

| File | What it covers |
| --- | --- |
| `test_storage.py` | Migrations, backups and their retention, the preload, the protection of the long term memory |
| `test_consolidation.py` | The nightly consolidation: updates, merges, translations, failures, lock, prune, dry run |
| `test_chatbot_memory.py` | What the chatbot reads and edits: `S:` / `L:` ids, search in both memories, corrections, forget requests |
| `test_memory_autonomy.py` | The top-right notification of what the chatbot wrote, and the instruction that makes it use the memory on its own |
| `test_shutdown.py` | The summary at closing (write-ahead), the lock of a dead process, the signals |
| `test_config.py` | Validation of the memory settings with fallback, and the comparison of live config files with the `.dist` |

`test/hardware/` has the scripts to try the sound hardware by hand. They are not part of the suite.
