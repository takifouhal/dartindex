.PHONY: install update clean

install:
	pyinstaller --onefile cli/main.py --name dartindex --add-data "cli/scip_pb2.py:."
	sudo mv dist/dartindex /usr/local/bin/
	sudo chmod +x /usr/local/bin/dartindex

update: clean install

clean:
	rm -rf build dist *.spec
	sudo rm -f /usr/local/bin/dartindex 