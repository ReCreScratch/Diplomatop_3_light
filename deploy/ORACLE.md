# Diplomatio kostenlos hosten (Oracle Cloud Always Free)

Ergebnis: Der Server läuft rund um die Uhr auf einer eigenen kleinen VM, Spielstände bleiben erhalten,
Mitspieler öffnen einfach `http://<IP der VM>`.

Dauer: ca. 30–60 Minuten, einmalig.

## 1. Konto anlegen
1. Auf <https://www.oracle.com/cloud/free/> registrieren. Eine Kreditkarte wird nur zur Verifizierung
   verlangt, für „Always Free“-Ressourcen wird nichts abgebucht.
2. Als **Home Region** eine nahe Region wählen, z. B. *Germany Central (Frankfurt)*. Sie lässt sich später
   nicht mehr ändern.

## 2. VM erstellen
1. Menü → *Compute* → *Instances* → **Create instance**.
2. **Image:** *Canonical Ubuntu* (aktuelle LTS-Version).
3. **Shape:** eine Form mit dem Hinweis *Always Free eligible* wählen, z. B. *VM.Standard.A1.Flex* (Ampere)
   mit 1 OCPU und 6 GB RAM, oder *VM.Standard.E2.1.Micro*. Für 12 Spieler reicht beides.
   Meldet Oracle „Out of capacity“, später erneut versuchen oder die andere Form nehmen.
4. **Networking:** Standard lassen und darauf achten, dass *Assign a public IPv4 address* aktiv ist.
5. **SSH keys:** *Generate a key pair for me* → **beide Schlüssel herunterladen** (z. B. nach
   `C:\Users\<du>\.ssh\oracle.key`).
6. **Create**. Nach 1–2 Minuten steht die **Public IP address** auf der Instanz-Seite.

## 3. Port 80 in der Cloud-Firewall öffnen
1. Auf der Instanz-Seite den Link unter *Virtual cloud network* öffnen → *Security Lists* →
   *Default Security List*.
2. **Add Ingress Rules:** Source CIDR `0.0.0.0/0`, IP Protocol *TCP*, Destination Port Range `80`.

(Die Firewall innerhalb der VM öffnet später das Setup-Skript.)

## 4. Per SSH verbinden
In PowerShell auf deinem PC:

```powershell
ssh -i $HOME\.ssh\oracle.key ubuntu@<PUBLIC-IP>
```

Meldet SSH „unprotected private key file“, den Zugriff auf den Schlüssel einschränken:

```powershell
icacls $HOME\.ssh\oracle.key /inheritance:r /grant:r "$($env:USERNAME):R"
```

## 5. Code auf die VM bringen
Das Repo ist privat, deshalb bekommt die VM einen eigenen Lesezugriff (Deploy Key):

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Die ausgegebene Zeile auf GitHub im Repo unter *Settings* → *Deploy keys* → *Add deploy key* einfügen
(nur Lesezugriff, kein Haken bei *Allow write access*). Dann:

```bash
git clone git@github.com:ReCreScratch/Diplomatop_3_light.git diplomatio
cd diplomatio
```

## 6. Einrichten und starten

```bash
bash deploy/setup.sh
```

Am Ende zeigt das Skript die Adresse an, z. B. `http://130.61.x.x`. Diese Adresse an die Mitspieler
schicken. Der Server startet nach einem VM-Neustart automatisch wieder.

## Updates einspielen
Nach neuen Commits auf GitHub:

```bash
cd ~/diplomatio && git pull && bash deploy/setup.sh
```

Laufende Spiele bleiben erhalten, sie liegen in `saves/`, und das ist nicht im Git.

## Nützliche Befehle

| Zweck | Befehl |
|---|---|
| Status | `sudo systemctl status diplomatio` |
| Live-Logs | `journalctl -u diplomatio -f` |
| Neustart | `sudo systemctl restart diplomatio` |
| Spielstände sichern (auf dem PC ausführen) | `scp -i $HOME\.ssh\oracle.key -r ubuntu@<PUBLIC-IP>:diplomatio/saves .` |

## Hinweise
- **Inaktivität:** Oracle kann Always-Free-VMs zurückfordern, die über längere Zeit fast keine Last
  erzeugen. Das trifft vor allem ungenutzte VMs. Bei regelmäßigem Spielen ist das kein Thema; im Zweifel
  vorher Spielstände sichern.
- **Offen im Internet:** Jeder mit der IP kann die Seite öffnen. Wer keine Fremden in der Lobby will,
  braucht einen Lobby-Passwortschutz (noch nicht eingebaut).
- **Kein HTTPS:** Die Verbindung ist unverschlüsselt (`http://`). Für ein Spiel unter Freunden in Ordnung;
  für HTTPS bräuchte es einen Domainnamen und z. B. Caddy davor.
