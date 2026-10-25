# wifi_lab4 – uruchamianie skryptu krok po kroku

Skrypt `wifi_lab4.py` wykonuje pomiary Iperf z protokołu ćwiczenia nr 4 (IEEE 802.11b/g/n) i zapisuje wyniki do CSV.

## 1. Wymagania

Na PC1 (serwer) i PC2 (klient):
- `iperf` w wersji 2.x (nie iperf3). Sprawdź: `iperf -v`.

Tylko na PC1:
- Python 3 (`python3 --version`).
- Dostęp `ssh` do PC2 bez hasła (klucz). Konfiguracja:
  ```
  ssh-keygen            # ENTER na wszystkie pytania
  ssh-copy-id user@IP_PC2
  ssh user@IP_PC2 iperf -v   # musi zadziałać bez pytania o hasło
  ```

## 2. Pobranie skryptu na PC1

```
git clone <adres_repo> various_scripts
cd various_scripts
git checkout claude/tender-tesla-01w2th
cd wifi_lab4
chmod +x wifi_lab4.py
```

## 3. Przygotowanie stanowiska

1. PC1 – AP1 (tryb AP) ))) (( AP2 (Client-bridge) – PC2, urządzenia ok. 2 m od siebie.
2. Skonfiguruj AP1 i AP2 według instrukcji (tab. 1 i 2): ten sam SSID, szyfrowanie wyłączone, moc AP2 10 mW.
3. Sprawdź adresy IP: `ip a` na PC1 i PC2. Zapisz je, będą potrzebne poniżej:
   - `IP_PC1` – adres PC1 (serwer Iperf),
   - `IP_PC2` – adres PC2,
   - `IP_AP1`, `IP_AP2` – adresy punktów dostępowych (instrukcja: 192.168.1.1 i 192.168.1.2).
4. Sprawdź łączność: `ping IP_PC2`, `ping IP_AP2`.

## 4. Uruchomienie pomiarów

Ogólna postać (wszystko w jednej linii albo z `\` na końcu linii):

```
./wifi_lab4.py --server-ip IP_PC1 --client-prefix "ssh user@IP_PC2" \
  --ap-ip IP_AP1 --client-ip IP_AP2 run SEKCJA
```

Najpierw sprawdź plan bez pomiarów (nic nie nadaje, nic nie pyta):

```
./wifi_lab4.py --server-ip IP_PC1 --client-prefix "ssh user@IP_PC2" --dry-run run 2.2
```
Wszystkie opcje z pkt 7 podawaj **przed** słowem `run`. Po `run` idą tylko sekcje oraz `--rate`, `--width`, `--frag`.

### Sekcje protokołu

| Komenda | Co mierzy |
|---|---|
| `run 2.2` | 802.11b, długa preambuła |
| `run 2.3` | 802.11b, krótka preambuła |
| `run 2.4` | 802.11g |
| `run 2.5` | 802.11n, 20 MHz, MIMO 1x1, 2x2, 3x3 |
| `run 2.6` | 802.11n, 40 MHz, MIMO 1x1, 2x2, 3x3 |
| `run 2.7 --rate R --width W` | wpływ długości pakietu UDP (R, W podaje protokół/prowadzący) |
| `run 2.8 --frag P1 P2 P3` | fragmentacja MAC, progi P podaje prowadzący |
| `run all` | wszystko po kolei (2.7 i 2.8 wymagają swoich parametrów) |

Przykłady:
```
./wifi_lab4.py --server-ip 192.168.1.100 --client-prefix "ssh user@192.168.1.101" --ap-ip 192.168.1.1 --client-ip 192.168.1.2 run 2.2
./wifi_lab4.py ... run 2.7 --rate 130 --width 20
./wifi_lab4.py ... run 2.8 --frag 256 512 1024
```

## 5. Co się dzieje podczas pomiaru

Dla każdej przepływności bitowej skrypt:
1. wypisuje: `>> Ustaw na Client-bridge: przeplywnosc=... Mbps ...` i czeka,
2. **Ty** ustawiasz tę przepływność w panelu AP2 (Client-bridge), a dla 2.8 także próg fragmentacji; potem ENTER,
3. skrypt robi `ping` do AP1 i AP2; przy błędzie prosi o wyłączenie i włączenie AP2, potem ENTER,
4. wykonuje 3 pomiary po 30 s (serwer Iperf lokalnie, klient przez ssh na PC2),
5. wypisuje wynik: przepustowość, jitter, utrata pakietów.

Przed sekcją 2.3 przełącz preambułę na krótką, przed 2.6 ustaw 40 MHz na obu AP (instrukcja 4.5), przed zmianą MIMO ustaw schemat na AP.

Przerwanie: `Ctrl+C` – dotychczasowe wyniki zostają zapisane.

## 6. Wyniki

Katalog `wyniki/`:
- `pomiary_DATA.csv` – każdy pomiar (przepustowość, jitter, utrata, stosunek do przepływności),
- `podsumowanie_DATA.csv` – średnie z powtórzeń.

Wartości przepisz do tabel protokołu. Kolumna `stosunek_do_przeplywnosci` jest wymagana w sprawozdaniu.

## 7. Przydatne opcje

| Opcja | Znaczenie |
|---|---|
| `--duration 10` | krótszy pomiar (domyślnie 30 s) |
| `--repeats 1` | jeden pomiar zamiast trzech |
| `--auto` | nie pytaj o ręczną zmianę ustawień |
| `--hook "komenda"` | komenda zmieniająca ustawienia AP (zmienne `WIFI_RATE`, `WIFI_WIDTH`, `WIFI_MIMO`, `WIFI_PREAMBLE`, `WIFI_FRAG`) |
| `--reset-hook "komenda"` | komenda resetująca Client-bridge po zerwaniu łączności |
| `--outdir katalog` | gdzie zapisać wyniki |
| `--iperf /sciezka/iperf` | inna binarka iperf |

## 8. Typowe problemy

- `ssh` pyta o hasło – wykonaj krok z kluczem (pkt 1).
- `brak raportu podsumowujacego serwera` – klient nie dotarł do serwera: sprawdź `--server-ip`, `ping`, zaporę (UDP, port 5001).
- Przepustowość 0 po zmianie przepływności – połączenie AP2 zerwane, zrestartuj Client-bridge.
