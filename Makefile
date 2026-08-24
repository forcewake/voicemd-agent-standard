.PHONY: test validate build release-examples

PYTHON ?= python3
PYTEST ?= pytest

test:
	PYTHONPATH=src $(PYTEST)

validate:
	PYTHONPATH=src $(PYTHON) -m voicemd validate --path templates/full/VOICE.md --strict
	PYTHONPATH=src $(PYTHON) -m voicemd validate --path templates/spoken/VOICE.md --strict

build:
	$(PYTHON) -m build --no-isolation

release-examples:
	PYTHONPATH=src $(PYTHON) -m voicemd compile --path templates/full/VOICE.md --profile executive_brief --output examples/compiled/executive.prompt.md
	PYTHONPATH=src $(PYTHON) -m voicemd compile --path templates/full/VOICE.md --profile nemotron_voicechat --format nemotron-ascii --compact --output examples/compiled/nemotron.prompt.txt
