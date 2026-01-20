IoT Access Control Gates (Raspberry Pi)

Prosty projekt bramek kontroli dostępu z komunikacją przez MQTT.

Opis
======
Projekt składa się z dwóch skryptów:
- `server.py` — serwer (uruchom na komputerze, który będzie brokerem/serwerem aplikacji)
- `gate.py` — klient bramki (np. na Raspberry Pi)

Komunikacja między nimi odbywa się przez MQTT.

Wymagania
---------
- Python 3
- Broker MQTT (np. Mosquitto)

Konfiguracja MQTT (Mosquitto)
-----------------------------
Na maszynie, na której uruchamiasz `server.py`, zainstaluj i skonfiguruj Mosquitto. Otwórz plik konfiguracyjny:

```bash
sudo nano /etc/mosquitto/mosquitto.conf
```

Dodaj na samym dole pliku następujące linie, aby nasłuchiwać na wszystkich interfejsach i zezwolić na anonimowy dostęp (tylko do testów!):

```
listener 1883 0.0.0.0
allow_anonymous true
```

Aby uruchomić usługę Mosquitto użyj:

```bash
sudo systemctl start mosquitto
```

Konfiguracja środowiska
-----------------------
Skopiuj plik przykładowy środowiska i edytuj wartości jeśli trzeba:

```bash
cp .env.example .env
nano .env
```

Zainstaluj zależności z pliku `requirements.txt` (używając `sudo`):

```bash
sudo pip install -r requirements.txt
```

Uruchamianie
------------
1. Uruchom broker MQTT na maszynie serwera (jeśli nie jest już uruchomiony).

2. Na maszynie przeznaczonej dla serwera uruchom (uruchamiaj z `sudo`):

```bash
sudo python3 server.py
```

3. Na Raspberry Pi z bramką uruchom (uruchamiaj z `sudo`):

```bash
sudo python3 gate.py
```

Po uruchomieniu obu skryptów będą się komunikować przez skonfigurowany broker MQTT.

Pliki
-----
- [.env.example](.env.example) — przykładowe zmienne środowiskowe
- `server.py` — serwer
- `gate.py` — klient / bramka
