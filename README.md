IoT Access Control Gates (Raspberry Pi)

Prosty projekt bramek kontroli dostępu z komunikacją przez MQTT.

Opis
======
Projekt składa się z trzech głównych skryptów:
- `server.py` — MQTT relay serwer (komunikacja między gate.py a backendem)
- `gate.py` — klient bramki kontroli dostępu (na Raspberry Pi)
- `rfid_server.py` — **Nowy** - interfejs do przypisywania kart RFID do użytkowników

Komunikacja między `gate.py` a `server.py` odbywa się przez MQTT.
Nowa funkcjonalność RFID Assignment jest obsługiwana przez dedykowany `rfid_server.py`.

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
### 1. Serwer MQTT Relay (dla control access)
```bash
sudo python3 server.py
```
- Serwer komunikuje się między `gate.py` a backendem przez MQTT
- Obsługuje żądania dostępu od bramek

### 2. Bramka (Gate - kontrola dostępu)
```bash
sudo python3 gate.py
```
- System czeka na kartę RFID
- Wybierz kierunek (zielony = wejście, czerwony = wyjście)
- Wysyła żądanie do serwera MQTT

### 3. RFID Server (przypisywanie kart)
```bash
sudo python3 rfid_server.py
```
- **Niezależny skrypt**
- Wciśnij przycisk zielony aby uruchomić interfejs przypisywania RFID
- Scrolluj encoderem, wybierz użytkownika, przyłóż kartę RFID
- Serwer wyśle żądanie do backendu aby przypisać kartę

**Uwaga**: Skrypty `server.py`, `gate.py` i `rfid_server.py` mogą działać równolegle, każdy na innej maszynie (RPi lub innym urządzeniu).
- Serwer weryfikuje dostęp i wyświetla rezultat

### Pełny Setup (Legacy)
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
- [server.py](server.py) — MQTT relay serwer dla control access
- [gate.py](gate.py) — bramka kontroli dostępu (RFID + kierunek)
- [rfid_server.py](rfid_server.py) — **Nowy** - interfejs przypisywania RFID
- [config.py](config.py) — konfiguracja GPIO

RFID Assignment
-------------------------------------
Możliwość powiązania RFID z użytkownikiem z poziomu servera.

**Przepływ:**
1. Wciśnij przycisk zielony na maszynie `rfid_server.py`
2. Serwer pobiera listę użytkowników bez RFID z backendu
3. Scrolluj encoderem aby wybrać użytkownika
4. Wciśnij zielony przycisk aby zatwierdzić
5. Przyłóż kartę RFID
6. Serwer wysyła żądanie przypisania do backendu
7. System wyświetli potwierdzenie

