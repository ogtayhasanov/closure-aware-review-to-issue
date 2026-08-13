.PHONY: validate reproduce test check

validate:
	python scripts/validate_public_snapshot.py

reproduce:
	python scripts/reproduce_all.py

test:
	python -m unittest discover -s tests -v

check: validate reproduce test
