PYTHON = python3
POETRY ?= poetry

ifeq ($(OS), Darwin)
	OPEN := open
else
	OPEN := xdg-open
endif

.PHONY: init
init:
	$(POETRY) install

.PHONY: update
update:
	$(POETRY) lock
	$(POETRY) install

.PHONY: pitxu
pitxu:
	@begin=$$(date +%s); \
	echo "Starting Pitxu... \n"; \
	make run; \
	echo "\nPitxu Ended...\n"; \
	end=$$(date +%s); \
	echo "Total time used: $$((end - begin)) s."

.PHONY: run
run:
	@$(POETRY) run main

.PHONY: sounddevices
sounddevices:
	@$(POETRY) run sounddevices

.PHONY: where-is-python
where-is-python:
	$(POETRY) run whereis python3