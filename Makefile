.PHONY: release clean


PROJECT_DIR=easy_profile

PYTHON ?= python


release: clean
	$(PYTHON) setup.py sdist bdist_wheel
	twine upload dist/*


clean:
	rm -rf dist/
	rm -rf build/
	rm -rf $(PROJECT_DIR)/__pycache__
	rm -f $(PROJECT_DIR)/*.pyc
