from backend.setup.setup import Setup
from twisted.internet import reactor
from yaml import load, SafeLoader
import sys

if __name__ == "__main__":
    # 26.10.2026: optionaler Pfad zur Konfiguration, z.B. `python main.py config.dummy.yml` fuer die
    # Dummy-Umgebung, ohne config.yml zu ueberschreiben. Ohne Argument wie bisher config.yml.
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yml"
    with open(config_path, "r") as file:
        config = load(file, SafeLoader)

    flowmachine = Setup(config)
    reactor.run()
