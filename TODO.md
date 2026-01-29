⚠️ Started on 2026-01-28, misses a lot

[ ] Show the ClassName in the logs.
[ ] Try to remove all wait_for_queue and rely only in wait_for_busy_flag
[ ] Mock correctly RawInputStream for Mic (fake the context!)
[ ] Mock correctly OutputStream for Speakers
[ ] Review idle mode (was: eyes!)
[ ] Thinking and Speaking effect should be bundled in the painter or the macros, and be set up as permanent callbacks, and control them from main (or else) via busy flags only.
[ ] Add any alert from a remainder into the chatbot's history, so it remembers having done so.
[ ] Chatbot Historic: `Download > Filter >Store > Load` at a new session
[ ] Now the Eyes statics are done by Canvas, not loading a new Image (which forced a clear() in eInk). Review if still happens (LCD doesn't)