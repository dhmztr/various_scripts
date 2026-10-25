# wifi_lab4

Automatyczne pomiary do protokołu ćwiczenia nr 4 (IEEE 802.11b/g/n, Iperf 2).

Uruchamiać na PC1 (serwer Iperf). Wymaga `iperf` 2.x na obu PC; klient na PC2 przez `--client-prefix "ssh user@PC2"`.

    ./wifi_lab4.py --server-ip IP_PC1 --client-prefix "ssh user@IP_PC2" --ap-ip 192.168.1.1 --client-ip 192.168.1.2 run 2.2 2.3 2.4 2.5 2.6
    ./wifi_lab4.py ... run 2.7 --rate 130 --width 20
    ./wifi_lab4.py ... run 2.8 --frag 256 512 1024

Wyniki: `wyniki/pomiary_*.csv` (wszystkie pomiary), `wyniki/podsumowanie_*.csv` (średnie, stosunek do przepływności).
Zmianę przepływności/szerokości/preambuły/fragmentacji na AP skrypt zleca ręcznie (ENTER) lub przez `--hook` (zmienne WIFI_RATE, WIFI_WIDTH, WIFI_MIMO, WIFI_PREAMBLE, WIFI_FRAG).
