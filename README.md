# Meeting Pipeline

Pipeline locale per riunioni in italiano e inglese, con trascrizioni indipendenti, diarizzazione, revisione mirata, glossari per progetto e profili vocali. Funziona da CLI, come servizio sul Mac e tramite tre skill Codex.

## Organizzazione

| Componente | Responsabilità |
|---|---|
| `src/meeting_pipeline/` | Motore, stato SQLite, adattatori, controlli, conoscenza, esportazione |
| `src/meeting_pipeline/recipes/` | Workflow `quality` e `fast` versionati |
| `skills/meeting-process/` | Avvio e controllo elaborazioni |
| `skills/meeting-review/` | Revisione di parole e attribuzioni |
| `skills/meeting-knowledge/` | Glossari e profili vocali |
| `tests/`, `.github/workflows/ci.yml` | Verifiche del software, senza audio privati né download dei modelli |
| `docs/` | Architettura, stato della qualità e sviluppo successivo |

Le skill sono interfacce al motore. La coda lavora anche senza Codex aperto. Un nuovo modello richiede un adattatore; un nuovo comportamento richiede una ricetta e test, non una copia delle skill.

## Installazione sul Mac

Python 3.12, Apple Silicon, `uv`, `ffmpeg`, git e strumenti Swift/Xcode per il runtime nativo.

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .
```

Se il runtime del precedente benchmark è disponibile, riusarlo:

```sh
.venv/bin/meet init --runtime-root /percorso/local-meeting-pipeline
.venv/bin/meet doctor
```

Per un'installazione nuova, `scripts/setup_runtime.py --path /percorso/runtime` scarica diversi GB, compila FluidAudio e prepara le versioni fissate. Poi eseguire `meet init --runtime-root /percorso/runtime`. La ricostruzione completa su un Mac pulito è una procedura da verificare; il riuso del runtime del benchmark è stato provato. I modelli Core ML sono scaricati dal runtime al primo utilizzo; le rappresentazioni vocali includono l'hash dei file effettivamente utilizzati.

```sh
.venv/bin/python scripts/install_local.py
# Per attivare anche il controllo della cartella ogni minuto:
.venv/bin/python scripts/install_local.py --service
```

I collegamenti delle skill sono creati in `~/.codex/skills` (o `$CODEX_HOME/skills`); il comando è in `~/.local/bin/meet`. Potrebbe essere necessario aprire una nuova chat per vedere le nuove skill. L'installer non sostituisce installazioni diverse già presenti.

Con `--service`, il package viene installato senza collegamenti al sorgente in `~/.local/share/meeting-pipeline/service-env`. Eventuali runtime sotto Documenti/Desktop/Download sono copiati nella cartella dati: macOS può negare a un servizio in background l'accesso a quelle cartelle. Il repository di sviluppo resta al suo posto. Dopo un aggiornamento del codice, rieseguire l'installer con `--service` per aggiornare la copia operativa; l'installer si ferma se un worker è occupato.

## Uso quotidiano

```sh
meet process "/percorso/riunione.mp3" --project ProgettoAlpha --language auto --recipe quality
meet jobs
meet review list JOB
```

Il profilo `quality` esegue Parakeet e Qwen sull'intero file, Nemotron-3 per gli speaker e approfondimenti Whisper limitati ai disaccordi. Community-1 controlla i casi di diarizzazione sospetti. Con `--speakers N` si dichiara il numero noto di persone che hanno parlato: oltre otto viene scelto Community-1 direttamente.

`fast` esegue Qwen soltanto sugli intervalli segnalati e può perdere errori che il primo motore considera sicuri. I punteggi di confidenza non sono percentuali di correttezza. Le soglie iniziali sono euristiche, da calibrare.

I risultati sono in `~/.local/share/meeting-pipeline/jobs/JOB/`: trascrizione Markdown, rapporto HTML locale con audio, candidati originali, motivazioni dei dubbi, manifest e audit. Aprire `review.html` nel browser del Mac. Gli output privati non sono nel repository.

### Cartella automatica

Inserire audio in `~/.local/share/meeting-pipeline/inbox/`. Il servizio aspetta che il file sia stabile; può leggere un file affiancato `riunione.mp3.json`:

```json
{"project":"ProgettoAlpha","language":"it","recipe":"quality","speakers":7}
```

Senza metadati, usa progetto `general`, lingua automatica e qualità. Al termine lascia il job in `needs_review` o `ready`. Solo i job senza dubbi sono esportati automaticamente nella `outbox` locale. La cartella Obsidian può essere configurata come destinazione in `config.json`, dopo aver scelto la collocazione desiderata. I job revisionati possono essere esportati con il comando sotto.

Comu/iPhone è una sorgente da integrare separatamente: questa versione automatizza da quando il file è sul Mac. Non abilita cloud backup né presume che il piano Starter esponga un trasferimento automatico.

### Revisione

```sh
meet review resolve JOB ISSUE --action keep
meet review resolve JOB ISSUE --action name --name "Persona confermata"
meet review resolve JOB ISSUE --action replace --text "Testo confermato ascoltando" --language it
meet export JOB --directory "/percorso/vault/Riunioni"
```

La sostituzione richiede Qwen ForcedAligner configurato: nuove parole ricevono nuovi timestamp. `keep` conserva il testo corrente; un nome vale per il job, mentre l'iscrizione nella banca vocale è un'operazione separata. Per esportare consapevolmente una bozza usare `--draft`. Non vengono sovrascritte note differenti già esistenti.

### Glossario

```sh
meet glossary add "Prodotto X" --alias "prodotto ex" --project ProgettoAlpha --language '*' --meaning "Nome commerciale"
meet glossary list
```

Le grafie canoniche sono hotword di Qwen; gli alias individuano casi da controllare. Non esiste una sostituzione indiscriminata e il testo resta nella lingua parlata. Le definizioni sono metadati descrittivi; l'adattatore attuale passa ad ASR soltanto i termini canonici.

### Profili vocali

```sh
meet voice enroll "Persona confermata" "/percorso/audio.mp3" --start 120 --end 135 --confirmed
meet voice list
```

Scegliere intervalli puliti con una sola voce e almeno sei secondi; preferire più campioni da riunioni differenti. Il motore propone candidati ma non forza un'identità. L'accettazione automatica è inizialmente disattivata; richiede soglia, margine e un rapporto di valutazione su registrazioni etichettate separate, inclusi interlocutori sconosciuti. La CLI registra tale rapporto, non ne verifica automaticamente la validità. Nuovi campioni disattivano l'accettazione automatica fino alla rivalutazione. Nessun campione attribuito automaticamente entra da solo nella banca vocale.

## Operazioni e sviluppo

```sh
meet doctor
meet watch --once
python -m unittest discover -s tests -v
launchctl print gui/$(id -u)/local.meeting-pipeline.inbox
# Per fermare il servizio installato:
launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/local.meeting-pipeline.inbox.plist"
```

Configurazione e SQLite sono sotto `MEETING_PIPELINE_HOME` (default `~/.local/share/meeting-pipeline`). Il worker acquisisce un lock, conserva checkpoint e ritenta i file falliti con attesa crescente. I file completati non vengono rielaborati ad ogni scansione. Modificare metadati/profili/ricetta e richiamare `process` crea una nuova esecuzione tracciata.

Vedi [architettura](docs/ARCHITECTURE.md) e [stato e prossimi passi](docs/ROADMAP.md). La prima versione non promette trascrizioni perfette né una banca vocale già calibrata. GitHub Actions verifica il software; gli audio e i modelli sono eseguiti sul Mac.
