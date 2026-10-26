#!/usr/bin/env python3
"""Automatyzacja pomiarow z cwiczenia nr 4 (IEEE 802.11b/g/n, Iperf 2) wg protokolu.

Uruchamiac na PC1 (serwer Iperf, strona AP). Klient Iperf (PC2, strona Client-bridge)
uruchamiany jest zdalnie przez --client-prefix (np. "ssh user@192.168.1.101"),
albo lokalnie, jesli prefiks pusty.

Zmiana przeplywnosci bitowej / szerokosci kanalu / preambuly / fragmentacji na AP
odbywa sie:
  * recznie (skrypt czeka na ENTER), albo
  * przez --hook "komenda" wywolywana z env: WIFI_STEP, WIFI_RATE, WIFI_WIDTH,
    WIFI_MIMO, WIFI_PREAMBLE, WIFI_FRAG (puste, gdy nie dotyczy).

Sekcje protokolu: 2.2 b-long, 2.3 b-short, 2.4 g, 2.5 n20 (1x1,2x2,3x3),
2.6 n40 (1x1,2x2,3x3), 2.7 dlugosc pakietu, 2.8 fragmentacja.

Przyklady:
  wifi_lab4.py --server-ip 192.168.1.100 --client-prefix "ssh user@192.168.1.101" \
      --ap-ip 192.168.1.1 --client-ip 192.168.1.2 run 2.2 2.3 2.4
  wifi_lab4.py ... run 2.7 --rate 130 --width 20
  wifi_lab4.py ... run 2.8 --frag 256 512 1024
  wifi_lab4.py ... run all --dry-run
"""
import argparse
import csv
import datetime
import os
import shlex
import statistics
import subprocess
import sys
import time

PACKET_LENGTHS = [64, 128, 256, 512, 1024, 1470, 1528, 2048, 2332]

RATES = {
    "b": [11, 5.5, 2, 1],
    "g": [54, 48, 36, 24, 18, 12, 9, 6],
    "n20_1x1": [6.5, 13, 19.5, 26, 39, 52, 58.5, 65],
    "n20_2x2": [13, 26, 39, 52, 78, 104, 117, 130],
    "n20_3x3": [19.5, 39, 58.5, 78, 117, 156, 175.5, 195],
    "n40_1x1": [13.5, 27, 40.5, 54, 81, 108, 121.5, 135],
    "n40_2x2": [27, 54, 81, 108, 162, 216, 243, 270],
    "n40_3x3": [40.5, 81, 121.5, 162, 243, 324, 364.5, 405],
}

# sekcja -> lista (etykieta, klucz tabeli RATES, szerokosc, mimo, preambula)
SECTIONS = {
    "2.2": [("802.11b long", "b", 20, "", "long")],
    "2.3": [("802.11b short", "b", 20, "", "short")],
    "2.4": [("802.11g", "g", 20, "", "")],
    "2.5": [("802.11n 20MHz %s" % m, "n20_" + m, 20, m, "") for m in ("1x1", "2x2", "3x3")],
    "2.6": [("802.11n 40MHz %s" % m, "n40_" + m, 40, m, "") for m in ("1x1", "2x2", "3x3")],
}


def log(msg):
    print("[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


class Lab:
    def __init__(self, a):
        self.a = a
        self.rows = []
        self.step = 0
        os.makedirs(a.outdir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = os.path.join(a.outdir, "pomiary_%s.csv" % stamp)
        self.fh = open(self.csv_path, "w", newline="")
        self.w = csv.writer(self.fh)
        self.w.writerow(["sekcja", "opis", "przeplywnosc_Mbps", "szer_MHz", "pakiet_B", "frag_B",
                         "pomiar", "przepustowosc_Mbps", "jitter_ms", "utracone_pct",
                         "stosunek_do_przeplywnosci"])

    def run(self, cmd, timeout=None):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

    def ping_ok(self, ip):
        if self.a.dry_run:
            return True
        return self.run("ping -c 3 -W 2 %s" % shlex.quote(ip)).returncode == 0

    def check_link(self):
        """Ping AP i klienta po kazdej zmianie ustawien (instr. 4.2 pkt 3)."""
        targets = [t for t in (self.a.ap_ip, self.a.client_ip) if t]
        for attempt in range(1, self.a.ping_retries + 1):
            if all(self.ping_ok(t) for t in targets):
                return True
            log("ping nieudany (proba %d/%d)" % (attempt, self.a.ping_retries))
            if self.a.reset_hook:
                log("reset Client-bridge: %s" % self.a.reset_hook)
                if not self.a.dry_run:
                    self.run(self.a.reset_hook)
                time.sleep(self.a.reset_wait)
            else:
                input("Zerwane polaczenie: wyl/wlacz router Client-bridge, po ponownym polaczeniu ENTER... ")
        return False

    def apply(self, rate=None, width=None, mimo="", preamble="", frag=""):
        """Zmiana ustawien na urzadzeniu (hook albo recznie)."""
        self.step += 1
        desc = "przeplywnosc=%s Mbps szer=%s MHz mimo=%s preambula=%s frag=%s" % (
            rate, width, mimo or "-", preamble or "-", frag or "-")
        if self.a.hook:
            env = dict(os.environ, WIFI_STEP=str(self.step), WIFI_RATE=str(rate or ""),
                       WIFI_WIDTH=str(width or ""), WIFI_MIMO=mimo, WIFI_PREAMBLE=preamble,
                       WIFI_FRAG=str(frag))
            log("hook: %s (%s)" % (self.a.hook, desc))
            if not self.a.dry_run:
                subprocess.run(self.a.hook, shell=True, env=env, check=True)
                time.sleep(self.a.settle)
        elif not self.a.auto and not self.a.dry_run:
            input(">> Ustaw na Client-bridge: %s\n   ENTER po zmianie... " % desc)
        if not self.check_link():
            raise SystemExit("Brak lacznosci po zmianie ustawien - przerwano.")

    def iperf_once(self, bw_mbps, length, t):
        a = self.a
        srv = "%s -s -u -w1m -i1 -l%d -y C" % (a.iperf, length)
        cli = "%s -c %s -u -w1m -i1 -b%gm -t%d -l%d" % (a.iperf, a.server_ip, bw_mbps, t, length)
        if a.client_prefix:
            cli = "%s %s" % (a.client_prefix, shlex.quote(cli))
        log("serwer: %s" % srv)
        log("klient: %s" % cli)
        if a.dry_run:
            return 0.0, 0.0, 0.0
        sp = subprocess.Popen(shlex.split(srv), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(1.0)
        try:
            c = self.run(cli, timeout=t + a.client_slack)
            if c.returncode != 0:
                log("klient zwrocil kod %d: %s" % (c.returncode, c.stderr.strip()[:200]))
            time.sleep(2.0)  # serwer drukuje raport po pakiecie FIN
        finally:
            sp.terminate()
            try:
                out, _ = sp.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                sp.kill()
                out, _ = sp.communicate()
        return parse_server_csv(out, t)

    def measure(self, section, desc, rate, width, length, frag, repeats, start_no):
        # -b: maksymalna teoretyczna przepustowosc dla danej przeplywnosci (UWAGA 1)
        bw = rate * self.a.bw_factor
        for i in range(repeats):
            tp, jit, loss = self.iperf_once(bw, length, self.a.duration)
            ratio = tp / rate if rate else 0.0
            log("%s %s: %g Mbps -> %.2f Mbps, jitter %.3f ms, utrata %.1f%%" % (
                section, desc, rate, tp, jit, loss))
            row = [section, desc, rate, width or "", length, frag, start_no + i,
                   "%.3f" % tp, "%.3f" % jit, "%.2f" % loss, "%.3f" % ratio]
            self.rows.append(row)
            self.w.writerow(row)
            self.fh.flush()

    def sec_rates(self, sec):
        from_rate = self.a.from_rate
        for label, key, width, mimo, pre in SECTIONS[sec]:
            if self.a.mimo and mimo != self.a.mimo:
                continue
            log("=== %s: %s ===" % (sec, label))
            n = 1
            for rate in RATES[key]:
                if from_rate is not None and rate != from_rate:
                    n += self.a.repeats
                    continue
                from_rate = None  # wznowienie dotyczy tylko pierwszego schematu
                self.apply(rate, width, mimo, pre)
                self.measure(sec, label, rate, width, self.a.length, "", self.a.repeats, n)
                n += self.a.repeats

    def sec_length(self):
        a = self.a
        if a.rate is None or a.width is None:
            raise SystemExit("2.7 wymaga --rate i --width (wg protokolu)")
        log("=== 2.7: dlugosc pakietu, %g Mbps, %d MHz ===" % (a.rate, a.width))
        self.apply(a.rate, a.width)
        n = 1
        for ln in PACKET_LENGTHS:
            self.measure("2.7", "len=%d" % ln, a.rate, a.width, ln, "", a.repeats, n)
            n += a.repeats

    def sec_frag(self):
        a = self.a
        if not a.frag:
            raise SystemExit("2.8 wymaga --frag PROG [PROG ...] (progi od prowadzacego)")
        rate = a.rate if a.rate is not None else 54
        log("=== 2.8: fragmentacja MAC, %g Mbps ===" % rate)
        n = 1
        for fr in a.frag:
            self.apply(rate, a.width, frag=fr)
            self.measure("2.8", "frag=%d" % fr, rate, a.width, a.length, fr, a.frag_repeats, n)
            n += a.frag_repeats

    def summary(self):
        path = self.csv_path.replace("pomiary_", "podsumowanie_")
        groups = {}
        for r in self.rows:
            groups.setdefault((r[0], r[1], r[2], r[4], r[5]), []).append(r)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sekcja", "opis", "przeplywnosc_Mbps", "pakiet_B", "frag_B", "n",
                        "sr_przepustowosc_Mbps", "sr_jitter_ms", "stosunek_do_przeplywnosci"])
            for (sec, desc, rate, ln, fr), rs in groups.items():
                tp = statistics.mean(float(x[7]) for x in rs)
                jt = statistics.mean(float(x[8]) for x in rs)
                w.writerow([sec, desc, rate, ln, fr, len(rs), "%.3f" % tp, "%.3f" % jt,
                            "%.3f" % (tp / rate if rate else 0)])
        log("zapisano: %s, %s" % (self.csv_path, path))


def parse_server_csv(text, duration):
    """Raport serwera Iperf 2 (-y C):
    ts,src,sport,dst,dport,id,interval,bytes,bps,jitter_ms,lost,total,lost_pct,outoforder
    Wiersz z interwalem 0.0-~duration = podsumowanie calego testu."""
    best = None
    for line in text.splitlines():
        p = line.strip().split(",")
        if len(p) < 13:
            continue
        try:
            start, end = (float(x) for x in p[6].split("-"))
            bps, jit, lost_pct = float(p[8]), float(p[9]), float(p[12])
        except ValueError:
            continue
        if start == 0.0 and end >= duration * 0.9:
            best = (bps / 1e6, jit, lost_pct)
    if best is None:
        log("UWAGA: brak raportu podsumowujacego serwera - zapisano 0")
        return 0.0, 0.0, 100.0
    return best


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server-ip", required=True, help="IP PC1 (serwer Iperf)")
    p.add_argument("--client-prefix", default="", help='prefiks uruchamiania klienta, np. "ssh user@pc2"')
    p.add_argument("--ap-ip", default="", help="IP AP (ping kontrolny)")
    p.add_argument("--client-ip", default="", help="IP AP w trybie Client-bridge (ping kontrolny)")
    p.add_argument("--iperf", default="iperf", help="binarka Iperf 2")
    p.add_argument("--duration", type=int, default=30, help="czas pomiaru [s] (tab. 3: 30)")
    p.add_argument("--length", type=int, default=1470, help="dlugosc UDP [B] (tab. 3: 1470)")
    p.add_argument("--repeats", type=int, default=3, help="powtorzenia na przeplywnosc (protokol: 3)")
    p.add_argument("--frag-repeats", type=int, default=2, help="powtorzenia na prog fragmentacji (protokol 2.8)")
    p.add_argument("--bw-factor", type=float, default=1.0,
                   help="-b = przeplywnosc * factor (UWAGA 1: teoretyczne maksimum)")
    p.add_argument("--hook", default="", help="komenda zmieniajaca ustawienia AP (env WIFI_*)")
    p.add_argument("--reset-hook", default="", help="komenda resetujaca Client-bridge po zerwaniu")
    p.add_argument("--reset-wait", type=int, default=60)
    p.add_argument("--settle", type=int, default=10, help="pauza po hooku [s]")
    p.add_argument("--auto", action="store_true", help="bez pytan o reczna zmiane ustawien")
    p.add_argument("--ping-retries", type=int, default=3)
    p.add_argument("--client-slack", type=int, default=30)
    p.add_argument("--outdir", default="wyniki")
    p.add_argument("--dry-run", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="uruchom sekcje protokolu")
    r.add_argument("sections", nargs="+", help="2.2 2.3 2.4 2.5 2.6 2.7 2.8 lub all")
    r.add_argument("--rate", type=float, help="przeplywnosc [Mbps] dla 2.7/2.8")
    r.add_argument("--width", type=int, help="szerokosc kanalu [MHz] dla 2.7/2.8")
    r.add_argument("--mimo", choices=["1x1", "2x2", "3x3"], help="2.5/2.6: tylko ten schemat MIMO")
    r.add_argument("--from-rate", type=float, help="2.x: zacznij od tej przeplywnosci (wznowienie)")
    r.add_argument("--frag", type=int, nargs="*", help="progi fragmentacji [B] dla 2.8")
    a = p.parse_args()

    valid = ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8"]
    secs = valid if a.sections == ["all"] else a.sections
    for s in secs:
        if s not in valid:
            p.error("nieznana sekcja %s" % s)

    lab = Lab(a)
    try:
        for s in secs:
            if s in SECTIONS:
                lab.sec_rates(s)
            elif s == "2.7":
                lab.sec_length()
            else:
                lab.sec_frag()
    except KeyboardInterrupt:
        log("przerwano")
    finally:
        lab.fh.close()
        lab.summary()


if __name__ == "__main__":
    sys.exit(main())
