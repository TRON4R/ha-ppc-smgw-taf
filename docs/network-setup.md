# Netzwerk-Einrichtung: Home Assistant und SMGW verbinden

Das PPC Smart Meter Gateway ist fix auf die IP `192.168.100.100` konfiguriert und lässt sich nicht ändern. Home Assistant läuft typischerweise im Router-Netzwerk auf einer Adresse wie `192.168.2.x`. Da diese beiden Netzbereiche nicht direkt miteinander kommunizieren, muss dem Home-Assistant-Server eine zweite IP-Adresse aus dem `192.168.100.x`-Bereich zugewiesen werden.

## Zweite IP-Adresse in Home Assistant einrichten

1. **Einstellungen → System → Netzwerk**
2. **Netzwerkschnittstellen konfigurieren** öffnen
3. **IPv4** aufklappen
4. **Statisch** auswählen (falls noch nicht aktiv)
5. **+ Adresse hinzufügen** anklicken
6. IP-Adresse eingeben, z. B. `192.168.100.12`
   - Die letzte Zahl (hier `12`) ist frei wählbar — solange keine andere IP `192.168.100.x` bereits vergeben ist
7. Netzmaske `255.255.255.0` prüfen (sollte automatisch korrekt sein)
8. **Speichern**

![Netzwerkschnittstellen konfigurieren in Home Assistant](network-setup.png)

## Hinweise

- Ein Neustart von Home Assistant ist nach der Änderung ggf. erforderlich.
- Je nach Setup (VM, Host-System) kann auch ein Reboot des gesamten Host-Rechners nötig sein, damit die neue IP aktiv wird.
- Die neue IP muss **nicht** als SMGW-URL eingetragen werden — die bleibt weiterhin `https://192.168.100.100/cgi-bin/hanservice.cgi`. Die zweite IP sorgt nur dafür, dass Home Assistant diese Adresse überhaupt erreichen kann.
