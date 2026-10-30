.PHONY: test integration

test:
	python3 -m unittest discover -s tests -v

integration:
	REX_LIVE=1 python3 -m unittest discover -s tests -p test_live.py -v
