PYTHON = python3
PIP = pip3
POETRY ?= poetry

ifeq (, $(shell which python ))
  $(error "PYTHON=$(PYTHON) not found in $(PATH)")
endif
PYTHON_VERSION_MIN=3.11
CURRENT_PYTHON_VERSION=$(shell $(PYTHON) -c "import sys;t='{v[0]}.{v[1]}'.format(v=list(sys.version_info[:2]));sys.stdout.write(t)")
PYTHON_VERSION_OK=$(shell $(PYTHON) -c 'import sys;print(int(float("%d.%d"% sys.version_info[0:2]) >= $(PYTHON_VERSION_MIN)))' )

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
# Use this for a run inside Poetry. Not recommended for Raspberry Pi as uses virtual environment.
	@begin=$$(date +%s); \
	echo "Starting Pitxu... \n"; \
	make run; \
	echo "\nPitxu Ended...\n"; \
	end=$$(date +%s); \
	echo "Total time used: $$((end - begin)) s."

.PHONY: pitxu-rpi
pitxu-rpi:
# WARNING! DO NOT USE
# Modern OS/Python are pointing out the difference between having Python budled to support internal applications,
#	not for the end user. That's why we should always use a Virtual Environment.
#	Keeping it here for knowledge sharing, but should not be used.
#
# Use this for a run outside Poetry. Raspberry Pi as uses OS-bundled Python. Run `make rpi-install` first!
	@begin=$$(date +%s); \
	echo "Starting Pitxu... \n"; \
	$(PYTHON) runner.py; \
	echo "\nPitxu Ended...\n"; \
	end=$$(date +%s); \
	echo "Total time used: $$((end - begin)) s."

.PHONY: run
run:
	@$(POETRY) run main

.PHONY: sounddevices
sounddevices:
	@$(POETRY) run sounddevices

.PHONY: clear
clear:
	@$(POETRY) run clear

.PHONY: test_matrix
test_matrix:
	@$(POETRY) run test_matrix

.PHONY: test_eink_multiline
test_eink_multiline:
	@$(POETRY) run test_eink_multiline

.PHONY: battery_status
battery_status:
	@$(POETRY) run battery_status

.PHONY: where-is-python
where-is-python:
	$(POETRY) run whereis $(PYTHON)

.PHONY: rpi-install
rpi-install:
# WARNING! DO NOT USE
# Modern OS/Python are pointing out the difference between having Python budled to support internal applications,
#	not for the end user. That's why we should always use a Virtual Environment.
#	Keeping it here for knowledge sharing, but should not be used.
#
# The Python bundled in the system has to have Python 3.11
# Check it or fail otherwise, stopping the execution.
ifeq ($(PYTHON_VERSION_OK),0)
  $(error "Needs Python Version $(PYTHON_VERSION_MIN) or above. Current Python version: $(CURRENT_PYTHON_VERSION)")
endif
# It is required to create the virtual environment and pull the dependencies.
# This way we ensure it should work with these.
	make init
# This creates the requirements file based on the dependencies above.
	$(POETRY) export -f requirements.txt --without-hashes > requirements.txt
# Now install them
	$(PIP) install -r requirements.txt