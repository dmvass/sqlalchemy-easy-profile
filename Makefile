.PHONY: patch minor major release clean


PROJECT_DIR=easy_profile

PYTHON ?= python


patch:
	bumpversion patch


minor:
	bumpversion minor


major:
	bumpversion major


release: clean
	$(PYTHON) setup.py sdist bdist_wheel
	twine upload dist/*


clean:
	rm -rf dist/
	rm -rf build/
	rm -rf $(PROJECT_DIR)/__pycache__
	rm -f $(PROJECT_DIR)/*.pyc
