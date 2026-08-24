.PHONY: test validate build release-examples

test:
	PYTHONPATH=src pytest

validate:
	PYTHONPATH=src python -m voicemd validate --path templates/full/VOICE.md --strict
	PYTHONPATH=src python -m voicemd validate --path templates/spoken/VOICE.md --strict

build:
	python -m build

release-examples:
	PYTHONPATH=src python -m voicemd compile --path templates/full/VOICE.md --profile executive_brief --output examples/compiled/executive.prompt.md
	PYTHONPATH=src python -m voicemd compile --path templates/full/VOICE.md --profile nemotron_voicechat --format nemotron-ascii --compact --output examples/compiled/nemotron.prompt.txt
