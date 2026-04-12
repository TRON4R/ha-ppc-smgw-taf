
# ha-ppc-smgw-han

<img src="custom_components/smgw_han/brand/icon.png" alt="SMGW Icon" width="128" align="left" style="margin-right: 16px;">

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TRON4R&repository=ha-ppc-smgw-han)

**Home Assistant Custom Integration zum Abruf __geeichter Tagesendwerte__ von PPC Smart Meter Gateways über die HAN-Schnittstelle.**

<a href="README.en.md">English version</a>

<br clear="left">

## Was macht diese Integration?

Die Integration verbindet sich einmal täglich mit dem PPC SMGW und ruft die offiziellen, eichrechtskonformen Tagesendwerte vom Zählerstand-Endpunkt ab. Sie berechnet:

- **Tagesverbrauch (gesamt)** — gesamter Stromverbrauch des Vortags
- **Tagesverbrauch (Zeitfenster 1)** — Verbrauch im ersten Tarifzeitraum (Standard: 00:00–04:59)
- **Tagesverbrauch (Zeitfenster 2)** — Verbrauch im zweiten Tarifzeitraum (Standard: 05:00–23:59)
- **Tageseinspeisung (gesamt)** — gesamte Netzeinspeisung des Vortags

Alle Sensoren sind kompatibel mit dem Home Assistant **Energie-Dashboard**.

## Unterschied zu ha-ppc-smgw

Die bestehende [ha-ppc-smgw](https://github.com/jannickfahlbusch/ha-ppc-smgw)-Integration fragt aktuelle Zählerstände in festen 10-Minuten-Intervallen ab (unabhängig von der Nutzereinstellung beim Setup). Einige Nutzer berichten, dass sie vom SMGW gesperrt wurden, weil die Abfragehäufigkeit als zu hoch eingestuft wurde. Diese Integration verfolgt einen anderen Ansatz:

- **Ein Abruf pro Tag** (5 HTTP-Requests insgesamt, zu einer konfigurierbaren Uhrzeit. Damit kein Risiko einer SMGW-Sperrung wegen Überbeanspruchung)
- **Geeichte Werte** vom Zählerstand-Endpunkt des SMGW (keine Live-Momentaufnahmen)
- **Exakte Tarifaufteilung** anhand des sekundengenauen Zählerstands zum konfigurierten Tarifwechselzeitpunkt
- **Keine Timing-Probleme** — die Werte basieren auf den offiziellen Tagesgrenzen des SMGW, nicht auf der lokalen Uhrzeit des „Home Assistant"-Servers

## Voraussetzungen

- PPC Smart Meter Gateway mit aktivierter HAN-Schnittstelle
- HAN-Zugangsdaten (Benutzername + Passwort) vom Messstellenbetreiber
- Der "Home Assistant"-Server und das SMGW müssen sich IP-technisch gegenseitig "sehen" können.

> [!TIP] **Test**
> - EINFACHE LÖSUNG FÜR DAS IP-ROUTING-PROBLEM
> **Home Assistant und SMGW im selben IP-Bereich erreichbar machen**
> Das SMGW ist unveränderbar auf `192.168.100.100` konfiguriert, Home Assistant läuft meist auf einer lokalen IP wie z.B. `192.168.2.x` o.ä.
> Wie du deinem HA-Server ganz einfach eine zweite IP im `192.168.100.x`-Netz gibst, erklärt die
> [Netzwerk-Einrichtungsanleitung](docs/network-setup.md).

## Installation

### HACS (empfohlen)

1. HACS in Home Assistant öffnen
2. Integrationen → Drei-Punkte-Menü → Benutzerdefinierte Repositories
3. `https://github.com/TRON4R/ha-ppc-smgw-han` als Integration hinzufügen
4. „PPC SMGW HAN Daily Import" installieren
5. Home Assistant neu starten

### Manuell

1. `custom_components/smgw_han/` in das `custom_components/`-Verzeichnis von Home Assistant kopieren
2. Home Assistant neu starten

## Konfiguration

1. Einstellungen → Geräte & Dienste → Integration hinzufügen
2. Nach „PPC SMGW HAN" suchen
3. Eingeben:
   - **URL**: URL der SMGW HAN-Schnittstelle (Standard: `https://192.168.100.100/cgi-bin/hanservice.cgi`)
   - **Benutzername** und **Passwort**: HAN-Zugangsdaten
   - **Start Standard-Tarif**: Uhrzeit des Tarifwechsels (Standard: 05:00, konfigurierbar)
   - **Abrufzeit**: Uhrzeit des täglichen Datenabrufs (Standard: 00:15)

## Sensoren

| Sensor | Beschreibung | Device Class | State Class |
|---|---|---|---|
| Tagesverbrauch gesamt | Gesamtverbrauch des Vortags | `energy` | `total` |
| Tagesverbrauch Zeitfenster 1 | Verbrauch Zeitfenster 1 (Mitternacht → Tarifwechsel) | `energy` | `total` |
| Tagesverbrauch Zeitfenster 2 | Verbrauch Zeitfenster 2 (Tarifwechsel → Mitternacht) | `energy` | `total` |
| Tageseinspeisung gesamt | Gesamteinspeisung des Vortags | `energy` | `total` |
| Zählerstand Verbrauch Endstand Vortag | Absoluter Zählerstand zu Tagesbeginn (00:00) | `energy` | `total_increasing` |
| Zählerstand Verbrauch Tarifwechsel 1 | Absoluter Zählerstand zum Tarifwechselzeitpunkt | `energy` | `total_increasing` |
| Zählerstand Einspeisung Endstand Vortag | Absoluter Einspeise-Zählerstand zu Tagesbeginn (00:00) | `energy` | `total_increasing` |
| Tagesdatum | Datum der zuletzt abgerufenen Daten | `date` | — |

## Dashboard-Kachel: Verbrauchshistorie (täglich)

**Voraussetzung:** [ApexCharts Card](https://github.com/RomRider/apexcharts-card) (über HACS installierbar)

![Verbrauchshistorie SMGW täglich](dashboard/verbrauchshistorie_taeglich.png)

Die Kachel zeigt die letzten 30 Tage als gestapeltes Balkendiagramm:
- **Go** (blau): Verbrauch im vergünstigten Zeitfenster (Zeitfenster 1)
- **Standard** (pink): Verbrauch im Normalpreis-Zeitfenster (Zeitfenster 2)
- **Tooltip** (mouse-over): Einzelwerte je Tarifsegment pro Tag
- **Kopfzeile**: kumulierter Gesamtverbrauch je Segment im angezeigten Zeitraum

### Einbindung

1. [`dashboard/verbrauchshistorie_taeglich.yaml`](dashboard/verbrauchshistorie_taeglich.yaml) herunterladen
2. In Home Assistant: Dashboard → Kachel hinzufügen → Manuelle Karte
3. YAML einfügen und die Entity-IDs auf die eigenen anpassen:
   - `sensor.octopus_smgw_tagesverbrauch_zeitfenster_2` → eigene Entity-ID für Zeitfenster 2
   - `sensor.octopus_smgw_tagesverbrauch_zeitfenster_1` → eigene Entity-ID für Zeitfenster 1

Die Entity-IDs findest du unter **Einstellungen → Geräte & Dienste → Entitäten**.

## Anwendungsfall

Diese Integration wurde primär für den **Octopus Energy Go-Tarif** in Deutschland entwickelt, der einen vergünstigten Strompreis zwischen **00:00 und 04:59:59** (Go-Tarif) und einen Normalpreis von **05:00 bis 23:59:59** bietet. Der Tarifwechselzeitpunkt ist aber über das GUI einstellbar. Falls du eine völlig andere Tarifstruktur nutzt, eröffne bitte ein [Issue](https://github.com/TRON4R/ha-ppc-smgw-han/issues) oder idealerweise gleich einen [Pull Request](https://github.com/TRON4R/ha-ppc-smgw-han/pulls), damit wir gemeinsam die Integration entsprechend erweitern können.

## Lizenz

MIT-Lizenz — siehe [LICENSE](LICENSE) für Details.
