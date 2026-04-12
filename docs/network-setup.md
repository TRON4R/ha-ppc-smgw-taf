# Netzwerk-Einrichtung: Home Assistant und SMGW verbinden

Das PPC Smart Meter Gateway ist fix auf die IP `192.168.100.100` konfiguriert und lässt sich nicht ändern. Home Assistant läuft typischerweise im Router-Netzwerk auf einer Adresse wie z.B. `192.168.2.12`. Da diese beiden Netzbereiche nicht direkt miteinander kommunizieren, muss dem "Home Assistant"-Server eine zweite IP-Adresse aus dem `192.168.100.x`-Bereich zugewiesen werden. Dies geht recht einfach wie folgt:

## Zweite IP-Adresse in Home Assistant einrichten

1. _**Einstellungen → System → Netzwerk**_
2. Dort im Abschnitt _Netzwerkschnittstellen konfigurieren_ den Bereich _IPv4_ aufklappen
3. _Statisch_ selektieren (falls nicht sowieso schon aktiv. Das ist nötig, weil _Automatisch_ (d.h. DHCP) und zwei IP-Adressen sich in HA gegenseitig ausschließen)
4. _+ Adresse hinzufügen_ anklicken
5. Im neuen Feld die _IP-Adresse_ eingeben, z. B. `192.168.100.12`
   - Die letzte Zahl (hier `12`) ist frei wählbar, solange diese IP im Bereich `192.168.100.x` nicht bereits vergeben ist.
6. Netzmaske `255.255.255.0` prüfen (sollte automatisch korrekt sein)
7. **Speichern**

![Netzwerkschnittstellen konfigurieren in Home Assistant](network-setup.png)

## Hinweise

- Ein Neustart von Home Assistant ist ggf. nach dieser Änderung erforderlich, damit sie wirksam wird.
- Je nach Setup (VM, Host-System) kann auch ein Reboot der Virtual Machine oder des gesamten Host-Rechners nötig sein, damit die neue IP aktiv wird.
- Die neue IP muss **nicht** als SMGW-URL eingetragen werden — die bleibt weiterhin `https://192.168.100.100/cgi-bin/hanservice.cgi`. Die neue IP sorgt nur dafür, dass Home Assistant die 192.168.100.100 überhaupt ohne irgendwelche komplizierten Routing-Tabellen erreichen kann.
- Wenn Du das SMGW auch von Deinem Rechner aus per Browser erreichen können willst, musst Du diesem ebenfalls eine zweite IP aus dem Bereich 192.168.100.x geben. Diese muss dann entsprechend am Ende eine andere Zahl als .100 (schon vom SMGW belegt) und der oben eingetragenen IP sein (schon vom Home Assistant Server belegt). Wie man das genau unter Windows, MacOS oder Linux macht, kann Dir jede gute KI (z.B. ChatGPT, Claude oder Gemini) erklären.
Alle meine Versuche, eine Anzeige der SMGW-Oberfläche innerhalb Home Assistant zu erreichen (um nicht meinem PC auch noch eine zweite IP geben zu müssen), sind leider fehlgeschlagen. Das BSI hat das SMGW absolut zugenagelt. Irgendjemand sagte mal treffend: die SMGW werden sich sogar einem Angriff vom Mars erfolgreich widersetzen. Weder ist die Einbindung als iFrame erlaubt, noch hilft es, z.B. per Nginx Proxy die limitierenden Header-Einträge ("X-FRAME-OPTIONS: deny") rauszufiltern. Denn am Ende scheitert man dann an Session-Cookies und anderen Späßchen und fliegt nach der erfolgreichen Anmeldung sofort wieder aus der Weboberfläche raus. Wer hier eine Lösung findet, die in HA nachhaltig funktioniert, **bitte melden!**
