# Mail-Assistent

Ein sicherheitsorientierter E-Mail-Agent: liest neue Mails aus einem Gmail-Postfach,
klassifiziert und analysiert sie über die Anthropic API (Claude) nach einem festen
Sicherheits-Regelwerk und setzt automatisch Gmail-Labels. Er versendet, leitet weiter
oder löscht **niemals** automatisch etwas — dafür ist immer eine menschliche Freigabe
nötig (siehe `mail_assistant/system_prompt.md`).

## Was der Agent automatisch tut

1. Fragt per Gmail API neue, noch nicht verarbeitete Mails im Posteingang ab.
2. Schickt jede Mail (als Daten, nicht als Anweisung) an Claude mit dem
   Sicherheits-System-Prompt zur Analyse (Kategorie, Priorität, Sicherheitsrisiko,
   Phishing-Verdacht, Antwortentwurf, empfohlene Aktion).
3. Setzt passende Gmail-Labels (z. B. `MailAssistent/Kategorie-Kunde`,
   `MailAssistent/Prioritaet-HOCH`, `MailAssistent/Sicherheitsrisiko`).
4. Schreibt das vollständige Analyseergebnis inkl. Antwortentwurf als JSON-Zeile
   in `logs/analysis_log.jsonl`.

Kein automatischer Versand, keine Weiterleitung, keine Löschung — Antwortentwürfe
liegen nur im Log, du prüfst und versendest sie selbst.

## Setup

### 1. Python-Abhängigkeiten

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Anthropic API-Key

In [console.anthropic.com](https://console.anthropic.com) unter "API Keys" einen
Key erstellen.

### 3. Gmail-OAuth einrichten

1. In der [Google Cloud Console](https://console.cloud.google.com) ein Projekt anlegen.
2. "Gmail API" aktivieren.
3. Unter "APIs & Services" -> "Credentials" einen OAuth-Client vom Typ
   **Desktop app** erstellen und die JSON-Datei herunterladen.
4. Die Datei als `credentials.json` im Projektverzeichnis ablegen (Pfad ist über
   `GMAIL_CREDENTIALS_PATH` konfigurierbar).

### 4. Konfiguration

```bash
cp .env.example .env
# .env öffnen und ANTHROPIC_API_KEY eintragen
```

### 5. Erster Lauf (Google-Login im Browser)

```bash
python -m mail_assistant.main
```

Beim ersten Start öffnet sich ein Browserfenster für die Google-Anmeldung; danach
wird ein `token.json` gespeichert, das für alle weiteren Läufe automatisch
wiederverwendet wird (kein erneuter Login nötig, solange der Token gültig bleibt).

## Automatischer, zeitgesteuerter Betrieb

### Variante A: Cronjob (Linux/macOS)

```bash
crontab -e
```

Zeile hinzufügen, um den Agenten alle 10 Minuten laufen zu lassen:

```
*/10 * * * * cd /pfad/zum/repo && /pfad/zum/repo/.venv/bin/python -m mail_assistant.main >> logs/cron.log 2>&1
```

### Variante B: systemd-Timer

`~/.config/systemd/user/mail-assistant.service`:

```ini
[Unit]
Description=Mail-Assistent Lauf

[Service]
Type=oneshot
WorkingDirectory=/pfad/zum/repo
ExecStart=/pfad/zum/repo/.venv/bin/python -m mail_assistant.main
```

`~/.config/systemd/user/mail-assistant.timer`:

```ini
[Unit]
Description=Mail-Assistent alle 10 Minuten

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min

[Install]
WantedBy=timers.target
```

Aktivieren:

```bash
systemctl --user enable --now mail-assistant.timer
```

## Konfigurierbare Umgebungsvariablen (`.env`)

| Variable | Bedeutung | Standard |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API-Key | — (erforderlich) |
| `ANTHROPIC_MODEL` | Verwendetes Modell | `claude-sonnet-5` |
| `GMAIL_CREDENTIALS_PATH` | Pfad zur OAuth-Client-JSON | `credentials.json` |
| `GMAIL_TOKEN_PATH` | Pfad zum gespeicherten Token | `token.json` |
| `MAX_EMAILS_PER_RUN` | Max. Mails pro Lauf | `20` |
| `MAIL_ASSISTANT_LOG` | Pfad zur JSONL-Logdatei | `logs/analysis_log.jsonl` |

## Sicherheitsmodell

Das komplette Regelwerk (E-Mail-Inhalte sind nie vertrauenswürdige Anweisungen,
keine Preisgabe von Geheimnissen, keine autonomen kritischen Aktionen wie Senden/
Löschen/Zahlungen, Phishing- und Sicherheitsrisiko-Erkennung, Freigabepflicht bei
Unsicherheit) steht vollständig in
[`mail_assistant/system_prompt.md`](mail_assistant/system_prompt.md) und wird bei
jedem Lauf unverändert als System-Prompt an Claude übergeben.
